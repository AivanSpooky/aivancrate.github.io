"""Заявки: создание, просмотр, смена статуса, выполнение (для Aivan)."""
from datetime import datetime, date, time
from flask import Blueprint, render_template, request, redirect, url_for, flash
from models import (
    db, Application, ApCompletion, Players, AivanLevels, Completions,
    APPLICATION_TYPE_ADD_COMPLETION,
    APPLICATION_STATUS_PENDING,
    APPLICATION_STATUS_ACCEPTED,
    APPLICATION_STATUS_REJECTED,
    APPLICATION_STATUS_QUESTIONS,
)
from routes.auth import login_required, get_current_player, is_aivan

applications_bp = Blueprint('applications', __name__)
AIVAN_PLAYER_ID = 1


@applications_bp.route('/applications')
@login_required
def list_applications():
    """Список заявок: для Aivan — все, для остальных — только свои."""
    player = get_current_player()
    if is_aivan():
        applications = Application.query.order_by(Application.created_at.desc()).all()
    else:
        applications = Application.query.filter_by(player_id=player.id).order_by(Application.created_at.desc()).all()
    app_ids = [a.id for a in applications]
    ap_completions = {apc.application_id: apc for apc in ApCompletion.query.filter(ApCompletion.application_id.in_(app_ids)).all()} if app_ids else {}
    levels = {l.id: l for l in AivanLevels.query.all()}
    players = {p.id: p for p in Players.query.all()}
    # Для Aivan: помечаем заявки, по которым у игрока уже есть прохождение (предупреждение о повторном добавлении)
    already_has_completion = {}
    if is_aivan() and app_ids:
        for a in applications:
            apc = ap_completions.get(a.id)
            if apc and a.type == APPLICATION_TYPE_ADD_COMPLETION:
                existing = Completions.query.filter_by(player_id=a.player_id, level_id=apc.level_id).first()
                already_has_completion[a.id] = existing is not None
    # Игрок, от имени которого пишется комментарий по заявкам (Aivan) — для отображения иконки в столбце комментария
    aivan_player = Players.query.get(AIVAN_PLAYER_ID)
    return render_template(
        'applications.html',
        applications=applications,
        ap_completions=ap_completions,
        levels=levels,
        players=players,
        is_aivan=is_aivan(),
        already_has_completion=already_has_completion,
        aivan_player=aivan_player,
    )


@applications_bp.route('/applications/new', methods=['GET', 'POST'])
@login_required
def new_application():
    """Подать заявку на добавление прохождения (type=1). Требуется уровень; опционально дата, время, ссылка на видео, комментарий."""
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
        player = get_current_player()
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
    if not apc:
        return
    c = Completions.query.filter_by(player_id=app.player_id, level_id=apc.level_id).first()
    if c:
        db.session.delete(c)


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
    # Установка «Принята» → добавить прохождение в БД (без двойного добавления)
    if new_status == APPLICATION_STATUS_ACCEPTED:
        created, already_existed = _apply_accepted(app)
        if already_existed:
            flash('У этого игрока уже есть прохождение данного уровня — запись в БД не добавлена повторно (заявка #%s).' % app_id, 'warning')
    app.status = new_status
    db.session.commit()
    return redirect(url_for('applications.list_applications'))


@applications_bp.route('/applications/<int:app_id>/execute', methods=['POST'])
@login_required
def execute_application(app_id):
    """Выполнить заявку (только Aivan): для type=1 — создать прохождение и установить статус Принята (без двойного добавления)."""
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
    return redirect(url_for('applications.list_applications'))
