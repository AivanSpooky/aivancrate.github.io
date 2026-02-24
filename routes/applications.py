"""Заявки: создание, просмотр, смена статуса, выполнение (для Aivan). Заявка на регистрацию — только для гостей."""
import os
import re
import uuid
from datetime import datetime, date, time, timedelta
from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app, make_response, send_from_directory
from werkzeug.security import generate_password_hash
from werkzeug.utils import secure_filename
from models import (
    db, Application, ApCompletion, ApRegistration, Players, AivanLevels, Completions, Punishment,
    APPLICATION_TYPE_ADD_COMPLETION,
    APPLICATION_TYPE_REGISTRATION,
    APPLICATION_STATUS_PENDING,
    APPLICATION_STATUS_ACCEPTED,
    APPLICATION_STATUS_REJECTED,
    APPLICATION_STATUS_QUESTIONS,
    PUNISHMENT_TYPE_BLOCK_APPLICATIONS,
)
from sqlalchemy import nulls_last
from routes.auth import login_required, get_current_player, is_aivan
from services.level_service import paginate_query

applications_bp = Blueprint('applications', __name__)
AIVAN_PLAYER_ID = 1
APPLICANT_TOKEN_COOKIE = 'aivancrate_applicant_token'
PER_PAGE_OPTIONS = [10, 25, 50, 0]
SORT_OPTIONS = [
    ('created_desc', 'app_sort_created_desc'),
    ('created_asc', 'app_sort_created_asc'),
    ('updated_desc', 'app_sort_updated_desc'),
    ('updated_asc', 'app_sort_updated_asc'),
]
APPLICANT_TOKEN_MAX_AGE = 365 * 24 * 60 * 60  # 1 год
VERSION_REGEX = re.compile(r'^\d+\.\d+$')
NICKNAME_ALLOWED_CHARS = set('abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789 _-')
ALLOWED_ICON_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}


def _get_applicant_token():
    return request.cookies.get(APPLICANT_TOKEN_COOKIE)


def _set_applicant_token_cookie(response, token):
    response.set_cookie(APPLICANT_TOKEN_COOKIE, token, max_age=APPLICANT_TOKEN_MAX_AGE, samesite='Lax')


def _registration_warnings(apr):
    """Предупреждения для модератора по заявке на регистрацию. Возвращает список ключей i18n."""
    warnings = []
    if Players.query.filter(Players.nickname.ilike(apr.nickname)).first():
        warnings.append('reg_warn_nick_exists')
    if not all(c in NICKNAME_ALLOWED_CHARS for c in apr.nickname):
        warnings.append('reg_warn_nick_chars')
    if not VERSION_REGEX.match(apr.version):
        warnings.append('reg_warn_version_format')
    return warnings


def _has_active_punishment_block_applications(player_id):
    """Есть ли у игрока активное (не отменённое) наказание «блокировка заявок»."""
    if not player_id:
        return False
    return Punishment.query.filter(
        Punishment.player_id == player_id,
        Punishment.type == PUNISHMENT_TYPE_BLOCK_APPLICATIONS,
        Punishment.cancelled_at.is_(None),
        Punishment.end_at > datetime.utcnow()
    ).first() is not None


@applications_bp.route('/applications')
@login_required
def list_applications():
    """Список заявок с пагинацией и фильтрами. Обычный пользователь: фильтр по статусу, сортировка. Aivan: + фильтр по типу и по игроку."""
    player = get_current_player()
    base = Application.query
    if not is_aivan():
        base = base.filter(Application.player_id == player.id)

    status_filter = request.args.get('status', '').strip()
    if status_filter:
        try:
            s = int(status_filter)
            if s in (APPLICATION_STATUS_PENDING, APPLICATION_STATUS_ACCEPTED, APPLICATION_STATUS_REJECTED, APPLICATION_STATUS_QUESTIONS):
                base = base.filter(Application.status == s)
        except (TypeError, ValueError):
            pass
    if is_aivan():
        type_filter = request.args.get('type', '').strip()
        if type_filter:
            try:
                t = int(type_filter)
                if t in (APPLICATION_TYPE_ADD_COMPLETION, APPLICATION_TYPE_REGISTRATION):
                    base = base.filter(Application.type == t)
            except (TypeError, ValueError):
                pass
        player_filter = request.args.get('player_id', '').strip()
        if player_filter:
            try:
                pid = int(player_filter)
                base = base.filter(Application.player_id == pid)
            except (TypeError, ValueError):
                pass

    sort = request.args.get('sort', 'created_desc')
    if sort == 'created_asc':
        base = base.order_by(Application.created_at.asc())
    elif sort == 'created_desc':
        base = base.order_by(Application.created_at.desc())
    elif sort == 'updated_asc':
        base = base.order_by(nulls_last(Application.updated_at.asc()), Application.created_at.desc())
    elif sort == 'updated_desc':
        base = base.order_by(nulls_last(Application.updated_at.desc()), Application.created_at.desc())
    else:
        base = base.order_by(Application.created_at.desc())

    page = request.args.get('page', 1, type=int)
    per_page_arg = request.args.get('per_page', 10)
    try:
        per_page = int(per_page_arg)
    except (TypeError, ValueError):
        per_page = 10
    if per_page <= 0:
        per_page = 0
    pagination = paginate_query(base, page, per_page)
    applications = pagination.items
    app_ids = [a.id for a in applications]

    ap_completions = {apc.application_id: apc for apc in ApCompletion.query.filter(ApCompletion.application_id.in_(app_ids)).all()} if app_ids else {}
    ap_registrations = {apr.application_id: apr for apr in ApRegistration.query.filter(ApRegistration.application_id.in_(app_ids)).all()} if app_ids else {}
    levels = {l.id: l for l in AivanLevels.query.all()}
    players_list = Players.query.filter(Players.display_this == True).order_by(Players.nickname).all()
    players = {p.id: p for p in Players.query.all()}
    already_has_completion = {}
    reg_warnings = {}
    if is_aivan() and app_ids:
        for a in applications:
            apc = ap_completions.get(a.id)
            if apc and a.type == APPLICATION_TYPE_ADD_COMPLETION:
                existing = Completions.query.filter_by(player_id=a.player_id, level_id=apc.level_id).first()
                already_has_completion[a.id] = existing is not None
            if a.type == APPLICATION_TYPE_REGISTRATION:
                apr = ap_registrations.get(a.id)
                if apr:
                    reg_warnings[a.id] = _registration_warnings(apr)
    aivan_player = Players.query.get(AIVAN_PLAYER_ID)

    def build_page_url(p):
        args = request.args.to_dict(flat=False)
        args['page'] = [str(p)]
        return url_for('applications.list_applications', **{k: v[0] if len(v) == 1 else v for k, v in args.items()})

    def build_per_page_url(pp):
        args = request.args.to_dict(flat=False)
        args['per_page'] = [str(pp)]
        args['page'] = ['1']
        return url_for('applications.list_applications', **{k: v[0] if len(v) == 1 else v for k, v in args.items()})

    return render_template(
        'applications.html',
        applications=applications,
        ap_completions=ap_completions,
        ap_registrations=ap_registrations,
        levels=levels,
        players=players,
        players_list=players_list,
        is_aivan=is_aivan(),
        already_has_completion=already_has_completion,
        reg_warnings=reg_warnings,
        aivan_player=aivan_player,
        pagination=pagination,
        per_page_options=PER_PAGE_OPTIONS,
        current_per_page=per_page if per_page > 0 else pagination.total,
        current_sort=sort,
        sort_options=SORT_OPTIONS,
        current_status=status_filter,
        current_type=request.args.get('type', '') if is_aivan() else '',
        current_player_id=request.args.get('player_id', '') if is_aivan() else '',
        build_page_url=build_page_url,
        build_per_page_url=build_per_page_url,
    )


@applications_bp.route('/applications/new', methods=['GET', 'POST'])
@login_required
def new_application():
    """Подать заявку на добавление прохождения (type=1). Требуется уровень; опционально дата, время, ссылка на видео, комментарий."""
    player = get_current_player()
    if _has_active_punishment_block_applications(player.id):
        flash(current_app.config.get('PUNISHMENT_BLOCK_APPLICATIONS_MSG') or 'Заявки заблокированы.', 'warning')
        return redirect(url_for('applications.list_applications'))
    if request.method == 'POST':
        level_id = request.form.get('level_id')
        completion_date_str = (request.form.get('completion_date') or '').strip() or None
        completion_time_str = (request.form.get('completion_time') or '').strip() or None
        video_url = (request.form.get('video_url') or '').strip() or None
        comment = (request.form.get('comment') or '').strip() or None
        try:
            level_id = int(level_id)
        except (TypeError, ValueError):
            return redirect(url_for('applications.new_application'))
        level = AivanLevels.query.get(level_id)
        if not level:
            return redirect(url_for('applications.new_application'))
        if _has_active_punishment_block_applications(player.id):
            flash(current_app.config.get('PUNISHMENT_BLOCK_APPLICATIONS_MSG') or 'Заявки заблокированы.', 'warning')
            return redirect(url_for('applications.list_applications'))
        existing = Completions.query.filter_by(player_id=player.id, level_id=level_id).first()
        if existing:
            return render_template('new_application.html', error='already_completed', levels=AivanLevels.query.order_by(AivanLevels.level_name).all())
        completion_date = None
        if completion_date_str:
            try:
                completion_date = datetime.strptime(completion_date_str, '%Y-%m-%d').date()
            except ValueError:
                pass
        completion_time = None
        if completion_time_str:
            try:
                # "HH:MM" или "HH:MM:SS"
                parts = completion_time_str.split(':')
                if len(parts) >= 2:
                    h, m = int(parts[0]), int(parts[1])
                    s = int(parts[2]) if len(parts) >= 3 else 0
                    completion_time = time(h, m, s)
            except (ValueError, IndexError):
                pass
        app = Application(
            player_id=player.id,
            type=APPLICATION_TYPE_ADD_COMPLETION,
            status=APPLICATION_STATUS_PENDING,
            created_at=datetime.utcnow(),
        )
        db.session.add(app)
        db.session.flush()
        apc = ApCompletion(
            application_id=app.id,
            level_id=level_id,
            player_id=player.id,
            completion_date=completion_date,
            completion_time=completion_time,
            video_url=video_url or '',
            comment=comment,
        )
        db.session.add(apc)
        db.session.commit()
        return redirect(url_for('applications.list_applications'))
    levels = AivanLevels.query.order_by(AivanLevels.level_name).all()
    return render_template('new_application.html', levels=levels)


@applications_bp.route('/applications/<int:app_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_completion_application(app_id):
    """Редактировать заявку на прохождение (type=1) при статусе «В ожидании» или «Есть вопросы». После сохранения — статус «В ожидании», обновляется время."""
    player = get_current_player()
    if _has_active_punishment_block_applications(player.id):
        flash(current_app.config.get('PUNISHMENT_BLOCK_APPLICATIONS_MSG') or 'Заявки заблокированы.', 'warning')
        return redirect(url_for('applications.list_applications'))
    app = Application.query.get_or_404(app_id)
    if app.player_id != player.id or app.type != APPLICATION_TYPE_ADD_COMPLETION:
        return redirect(url_for('applications.list_applications'))
    if app.status not in (APPLICATION_STATUS_PENDING, APPLICATION_STATUS_QUESTIONS):
        return redirect(url_for('applications.list_applications'))
    apc = ApCompletion.query.filter_by(application_id=app.id).first()
    if not apc:
        return redirect(url_for('applications.list_applications'))
    levels = AivanLevels.query.order_by(AivanLevels.level_name).all()
    if request.method == 'POST':
        level_id = request.form.get('level_id')
        completion_date_str = (request.form.get('completion_date') or '').strip() or None
        completion_time_str = (request.form.get('completion_time') or '').strip() or None
        video_url = (request.form.get('video_url') or '').strip() or None
        comment = (request.form.get('comment') or '').strip() or None
        try:
            level_id = int(level_id)
        except (TypeError, ValueError):
            return redirect(url_for('applications.edit_completion_application', app_id=app_id))
        level = AivanLevels.query.get(level_id)
        if not level:
            return redirect(url_for('applications.edit_completion_application', app_id=app_id))
        if level_id != apc.level_id:
            existing = Completions.query.filter_by(player_id=player.id, level_id=level_id).first()
            if existing:
                return render_template('edit_completion.html', app=app, apc=apc, levels=levels, error='already_completed')
        completion_date = None
        if completion_date_str:
            try:
                completion_date = datetime.strptime(completion_date_str, '%Y-%m-%d').date()
            except ValueError:
                pass
        completion_time = None
        if completion_time_str:
            try:
                parts = completion_time_str.split(':')
                if len(parts) >= 2:
                    h, m = int(parts[0]), int(parts[1])
                    s = int(parts[2]) if len(parts) >= 3 else 0
                    completion_time = time(h, m, s)
            except (ValueError, IndexError):
                pass
        apc.level_id = level_id
        apc.completion_date = completion_date
        apc.completion_time = completion_time
        apc.video_url = video_url or ''
        apc.comment = comment
        app.status = APPLICATION_STATUS_PENDING
        app.updated_at = datetime.utcnow()
        db.session.commit()
        flash('Заявка обновлена и снова отправлена на рассмотрение.', 'success')
        return redirect(url_for('applications.list_applications'))
    return render_template('edit_completion.html', app=app, apc=apc, levels=levels)


def _apply_accepted(app):
    """Создать запись прохождения по заявке type=1. Возвращает (created, already_existed)."""
    if app.type != APPLICATION_TYPE_ADD_COMPLETION:
        return False, False
    apc = ApCompletion.query.filter_by(application_id=app.id).first()
    if not apc:
        return False, False
    existing = Completions.query.filter_by(player_id=app.player_id, level_id=apc.level_id).first()
    if existing:
        return False, True
    compl_date = apc.completion_date or date.today()
    c = Completions(
        level_id=apc.level_id,
        player_id=app.player_id,
        completion_date=compl_date,
        completion_time=apc.completion_time,
    )
    db.session.add(c)
    return True, False


def _revert_accepted(app):
    """Удалить запись прохождения, созданную по этой заявке (при снятии статуса Принята). Удаляет не более одной записи."""
    if app.type != APPLICATION_TYPE_ADD_COMPLETION:
        return
    apc = ApCompletion.query.filter_by(application_id=app.id).first()
    if not apc or not app.player_id:
        return
    c = Completions.query.filter_by(player_id=app.player_id, level_id=apc.level_id).first()
    if c:
        db.session.delete(c)


def _apply_registration(app):
    """Принять заявку на регистрацию: создать игрока, сохранить иконку в player_icons, привязать заявку к игроку."""
    if app.type != APPLICATION_TYPE_REGISTRATION:
        return False
    apr = ApRegistration.query.filter_by(application_id=app.id).first()
    if not apr:
        return False
    upload_root = current_app.config.get('UPLOAD_FOLDER') or os.path.join(current_app.instance_path, 'uploads')
    reg_icons = os.path.join(upload_root, current_app.config.get('REGISTRATION_ICONS_FOLDER', 'registration_icons'))
    src_path = os.path.join(reg_icons, apr.icon_filename)
    static_icons = os.path.join(current_app.root_path, 'static', 'images', 'player_icons')
    os.makedirs(static_icons, exist_ok=True)
    ext = os.path.splitext(apr.icon_filename)[1] or '.png'
    new_filename = 'reg_%s%s' % (app.id, ext)
    dest_path = os.path.join(static_icons, new_filename)
    if os.path.isfile(src_path):
        import shutil
        shutil.copy2(src_path, dest_path)
    else:
        new_filename = 'aivan.png'
    player = Players(
        nickname=apr.nickname.strip(),
        version=apr.version.strip(),
        icon=new_filename,
        display_this=True,
        password_hash=apr.password_hash,
    )
    db.session.add(player)
    db.session.flush()
    app.player_id = player.id
    return True


@applications_bp.route('/applications/<int:app_id>/status', methods=['POST'])
@login_required
def set_status(app_id):
    """Изменить статус и/или комментарий заявки (только Aivan). При статусе Принята — создать прохождение в БД; при снятии Принята — удалить."""
    if not is_aivan():
        return redirect(url_for('applications.list_applications'))
    app = Application.query.get_or_404(app_id)
    app.notes = request.form.get('notes', app.notes)
    app.updated_at = datetime.utcnow()
    if request.form.get('save_notes'):
        db.session.commit()
        return redirect(url_for('applications.list_applications'))
    new_status = request.form.get('status')
    try:
        new_status = int(new_status)
    except (TypeError, ValueError):
        db.session.commit()
        return redirect(url_for('applications.list_applications'))
    if new_status not in (APPLICATION_STATUS_PENDING, APPLICATION_STATUS_ACCEPTED, APPLICATION_STATUS_REJECTED, APPLICATION_STATUS_QUESTIONS):
        db.session.commit()
        return redirect(url_for('applications.list_applications'))
    old_status = app.status
    # Снятие «Принята» → удалить прохождение из БД (один раз)
    if old_status == APPLICATION_STATUS_ACCEPTED and new_status != APPLICATION_STATUS_ACCEPTED:
        _revert_accepted(app)
    # Установка «Принята» → добавить прохождение (type=1) или выполнить регистрацию (type=2)
    if new_status == APPLICATION_STATUS_ACCEPTED:
        if app.type == APPLICATION_TYPE_ADD_COMPLETION:
            created, already_existed = _apply_accepted(app)
            if already_existed:
                flash('У этого игрока уже есть прохождение данного уровня — запись в БД не добавлена повторно (заявка #%s).' % app_id, 'warning')
        elif app.type == APPLICATION_TYPE_REGISTRATION:
            _apply_registration(app)
    app.status = new_status
    db.session.commit()
    return redirect(url_for('applications.list_applications'))


@applications_bp.route('/applications/<int:app_id>/execute', methods=['POST'])
@login_required
def execute_application(app_id):
    """Выполнить заявку (только Aivan): type=1 — прохождение, type=2 — регистрация."""
    if not is_aivan():
        return redirect(url_for('applications.list_applications'))
    app = Application.query.get_or_404(app_id)
    if app.status != APPLICATION_STATUS_PENDING:
        return redirect(url_for('applications.list_applications'))
    if app.type == APPLICATION_TYPE_ADD_COMPLETION:
        created, already_existed = _apply_accepted(app)
        if already_existed:
            flash('У этого игрока уже есть прохождение данного уровня — запись в БД не добавлена повторно (заявка #%s).' % app_id, 'warning')
        app.status = APPLICATION_STATUS_ACCEPTED
        app.updated_at = datetime.utcnow()
        db.session.commit()
    elif app.type == APPLICATION_TYPE_REGISTRATION:
        _apply_registration(app)
        app.status = APPLICATION_STATUS_ACCEPTED
        app.updated_at = datetime.utcnow()
        db.session.commit()
    return redirect(url_for('applications.list_applications'))


# --- Заявка на регистрацию (только для гостей) ---

@applications_bp.route('/uploads/registration_icons/<path:filename>')
def serve_registration_icon(filename):
    """Раздача загруженных иконок заявок на регистрацию."""
    upload_root = current_app.config.get('UPLOAD_FOLDER') or os.path.join(current_app.instance_path, 'uploads')
    folder = os.path.join(upload_root, current_app.config.get('REGISTRATION_ICONS_FOLDER', 'registration_icons'))
    return send_from_directory(folder, filename)


@applications_bp.route('/registration', methods=['GET', 'POST'])
def new_registration_application():
    """Подать заявку на регистрацию. Доступно только неавторизованным."""
    if get_current_player():
        return redirect(url_for('auth.login'))
    if request.method == 'POST':
        nickname = (request.form.get('nickname') or '').strip()
        version = (request.form.get('version') or '').strip()
        password = request.form.get('password') or ''
        comment = (request.form.get('comment') or '').strip() or None
        icon_file = request.files.get('icon')
        errors = []
        if not nickname:
            errors.append('reg_err_nick_required')
        elif Players.query.filter(Players.nickname.ilike(nickname)).first():
            errors.append('reg_err_nick_exists')
        elif not all(c in NICKNAME_ALLOWED_CHARS for c in nickname):
            errors.append('reg_err_nick_chars')
        if not version:
            errors.append('reg_err_version_required')
        elif not VERSION_REGEX.match(version):
            errors.append('reg_err_version_format')
        if not password or len(password) < 6:
            errors.append('auth_password_short')
        if not icon_file or icon_file.filename == '':
            errors.append('reg_err_icon_required')
        else:
            ext = (secure_filename(icon_file.filename) or '').split('.')[-1].lower()
            if ext not in ALLOWED_ICON_EXTENSIONS:
                errors.append('reg_err_icon_format')
        if errors:
            return render_template('new_registration.html', errors=errors, nickname=nickname, version=version, comment=comment)
        token = _get_applicant_token() or uuid.uuid4().hex
        recent = Application.query.filter(
            Application.type == APPLICATION_TYPE_REGISTRATION,
            Application.applicant_token == token,
            Application.created_at >= datetime.utcnow() - timedelta(days=1)
        ).first()
        if recent:
            return render_template('new_registration.html', errors=['reg_err_one_per_day'], nickname=nickname, version=version)
        upload_root = current_app.config.get('UPLOAD_FOLDER') or os.path.join(current_app.instance_path, 'uploads')
        reg_folder = os.path.join(upload_root, current_app.config.get('REGISTRATION_ICONS_FOLDER', 'registration_icons'))
        os.makedirs(reg_folder, exist_ok=True)
        icon_filename = '%s.%s' % (token[:16], ext)
        icon_path = os.path.join(reg_folder, icon_filename)
        icon_file.save(icon_path)
        app = Application(
            player_id=None,
            applicant_token=token,
            type=APPLICATION_TYPE_REGISTRATION,
            status=APPLICATION_STATUS_PENDING,
            created_at=datetime.utcnow(),
        )
        db.session.add(app)
        db.session.flush()
        apr = ApRegistration(
            application_id=app.id,
            nickname=nickname,
            version=version,
            password_hash=generate_password_hash(password, method='pbkdf2:sha256'),
            icon_filename=icon_filename,
            comment=comment,
        )
        db.session.add(apr)
        db.session.commit()
        resp = make_response(redirect(url_for('applications.list_my_registration_applications')))
        _set_applicant_token_cookie(resp, token)
        return resp
    return render_template('new_registration.html')


@applications_bp.route('/registration/my')
def list_my_registration_applications():
    """Мои заявки на регистрацию (по cookie). Только для гостей."""
    if get_current_player():
        return redirect(url_for('applications.list_applications'))
    token = _get_applicant_token()
    if not token:
        applications = []
        ap_registrations = {}
    else:
        applications = Application.query.filter_by(applicant_token=token, type=APPLICATION_TYPE_REGISTRATION).order_by(Application.created_at.desc()).all()
        app_ids = [a.id for a in applications]
        ap_registrations = {apr.application_id: apr for apr in ApRegistration.query.filter(ApRegistration.application_id.in_(app_ids)).all()} if app_ids else {}
    aivan_player = Players.query.get(AIVAN_PLAYER_ID)
    return render_template(
        'my_registration_applications.html',
        applications=applications,
        ap_registrations=ap_registrations,
        aivan_player=aivan_player,
    )


@applications_bp.route('/registration/<int:app_id>/edit', methods=['GET', 'POST'])
def edit_registration_application(app_id):
    """Редактировать заявку на регистрацию при статусе «В ожидании» или «Есть вопросы» (по cookie)."""
    if get_current_player():
        return redirect(url_for('applications.list_applications'))
    app = Application.query.get_or_404(app_id)
    if app.type != APPLICATION_TYPE_REGISTRATION or app.applicant_token != _get_applicant_token():
        return redirect(url_for('applications.list_my_registration_applications'))
    if app.status not in (APPLICATION_STATUS_PENDING, APPLICATION_STATUS_QUESTIONS):
        return redirect(url_for('applications.list_my_registration_applications'))
    apr = ApRegistration.query.filter_by(application_id=app.id).first()
    if not apr:
        return redirect(url_for('applications.list_my_registration_applications'))
    if request.method == 'POST':
        nickname = (request.form.get('nickname') or '').strip()
        version = (request.form.get('version') or '').strip()
        password = request.form.get('password') or ''
        comment = (request.form.get('comment') or '').strip() or None
        icon_file = request.files.get('icon')
        errors = []
        if not nickname:
            errors.append('reg_err_nick_required')
        elif nickname != apr.nickname and Players.query.filter(Players.nickname.ilike(nickname)).first():
            errors.append('reg_err_nick_exists')
        elif not all(c in NICKNAME_ALLOWED_CHARS for c in nickname):
            errors.append('reg_err_nick_chars')
        if not version:
            errors.append('reg_err_version_required')
        elif not VERSION_REGEX.match(version):
            errors.append('reg_err_version_format')
        if password and len(password) < 6:
            errors.append('auth_password_short')
        new_icon_filename = apr.icon_filename
        if icon_file and icon_file.filename:
            ext = (secure_filename(icon_file.filename) or '').split('.')[-1].lower()
            if ext not in ALLOWED_ICON_EXTENSIONS:
                errors.append('reg_err_icon_format')
            else:
                upload_root = current_app.config.get('UPLOAD_FOLDER') or os.path.join(current_app.instance_path, 'uploads')
                reg_folder = os.path.join(upload_root, current_app.config.get('REGISTRATION_ICONS_FOLDER', 'registration_icons'))
                os.makedirs(reg_folder, exist_ok=True)
                new_icon_filename = 'edit_%s_%s.%s' % (app_id, uuid.uuid4().hex[:8], ext)
                icon_file.save(os.path.join(reg_folder, new_icon_filename))
        if errors:
            return render_template('edit_registration.html', app=app, apr=apr, errors=errors, nickname=nickname, version=version, comment=comment)
        apr.nickname = nickname
        apr.version = version
        apr.comment = comment
        if password:
            apr.password_hash = generate_password_hash(password, method='pbkdf2:sha256')
        apr.icon_filename = new_icon_filename
        app.status = APPLICATION_STATUS_PENDING
        app.updated_at = datetime.utcnow()
        db.session.commit()
        flash('Заявка обновлена и снова отправлена на рассмотрение.', 'success')
        return redirect(url_for('applications.list_my_registration_applications'))
    return render_template('edit_registration.html', app=app, apr=apr, errors=[], comment=apr.comment)


# ——— Наказания (только для Aivan) ———

@applications_bp.route('/punishments')
@login_required
def punishments_list():
    """Список всех наказаний. Только Aivan. Сортировка по игроку, статусы «в силе» / «прошло»."""
    if not is_aivan():
        return redirect(url_for('applications.list_applications'))
    player_id_filter = request.args.get('player_id', '').strip()
    base = Punishment.query
    if player_id_filter:
        try:
            base = base.filter(Punishment.player_id == int(player_id_filter))
        except ValueError:
            pass
    base = base.order_by(Punishment.created_at.desc())
    punishments = base.all()
    players = {p.id: p for p in Players.query.all()}
    players_list = Players.query.filter(Players.display_this == True).order_by(Players.nickname).all()
    return render_template(
        'punishments_list.html',
        punishments=punishments,
        players=players,
        players_list=players_list,
        current_player_id=player_id_filter,
    )


@applications_bp.route('/punishments/add', methods=['GET', 'POST'])
@login_required
def punishments_add():
    """Добавить наказание: игрок, тип, длительность (минуты/часы/дни), комментарий. Только Aivan."""
    if not is_aivan():
        return redirect(url_for('applications.list_applications'))
    if request.method == 'POST':
        player_id = request.form.get('player_id')
        ptype = request.form.get('type')
        amount = request.form.get('amount')
        unit = request.form.get('unit')  # minutes, hours, days
        notes = (request.form.get('notes') or '').strip() or None
        errors = []
        try:
            player_id = int(player_id)
        except (TypeError, ValueError):
            errors.append('pun_err_player')
        if not ptype or int(ptype) != PUNISHMENT_TYPE_BLOCK_APPLICATIONS:
            errors.append('pun_err_type')
        try:
            amount = float(amount)
            if amount <= 0:
                raise ValueError('must be positive')
        except (TypeError, ValueError):
            errors.append('pun_err_duration')
        if unit not in ('minutes', 'hours', 'days'):
            errors.append('pun_err_duration')
        if not errors and not Players.query.get(player_id):
            errors.append('pun_err_player')
        if errors:
            players_list = Players.query.filter(Players.display_this == True).order_by(Players.nickname).all()
            return render_template(
                'punishments_add.html',
                players_list=players_list,
                errors=errors,
                player_id=request.form.get('player_id'),
                type=request.form.get('type'),
                amount=request.form.get('amount'),
                unit=request.form.get('unit'),
                notes=request.form.get('notes'),
            )
        now = datetime.utcnow()
        if unit == 'minutes':
            delta = timedelta(minutes=amount)
        elif unit == 'hours':
            delta = timedelta(hours=amount)
        else:
            delta = timedelta(days=amount)
        end_at = now + delta
        pun = Punishment(
            player_id=player_id,
            type=PUNISHMENT_TYPE_BLOCK_APPLICATIONS,
            created_at=now,
            end_at=end_at,
            notes=notes,
        )
        db.session.add(pun)
        db.session.commit()
        flash(current_app.config.get('PUNISHMENT_ADDED_MSG') or 'Наказание добавлено.', 'success')
        return redirect(url_for('applications.punishments_list'))
    players_list = Players.query.filter(Players.display_this == True).order_by(Players.nickname).all()
    return render_template('punishments_add.html', players_list=players_list, errors=[])


@applications_bp.route('/punishments/<int:pun_id>/cancel', methods=['POST'])
@login_required
def punishment_cancel(pun_id):
    """Отменить наказание. Только Aivan/модераторы."""
    if not is_aivan():
        return redirect(url_for('applications.list_applications'))
    pun = Punishment.query.get_or_404(pun_id)
    if pun.cancelled_at is not None:
        flash('Наказание уже отменено.', 'info')
    else:
        pun.cancelled_at = datetime.utcnow()
        db.session.commit()
        flash('Наказание отменено.', 'success')
    player_id = request.form.get('player_id', '').strip()
    if player_id:
        return redirect(url_for('applications.punishments_list', player_id=player_id))
    return redirect(url_for('applications.punishments_list'))
