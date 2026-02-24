"""Заявки: создание, просмотр, смена статуса, выполнение (для Aivan)."""
from datetime import datetime, date
from flask import Blueprint, render_template, request, redirect, url_for, flash
from models import (
    db, Application, Players, AivanLevels, Completions,
    APPLICATION_TYPE_ADD_COMPLETION,
    APPLICATION_STATUS_PENDING,
    APPLICATION_STATUS_ACCEPTED,
    APPLICATION_STATUS_REJECTED,
    APPLICATION_STATUS_QUESTIONS,
)
from routes.auth import login_required, get_current_player, is_aivan

applications_bp = Blueprint('applications', __name__)


@applications_bp.route('/applications')
@login_required
def list_applications():
    """Список заявок: для Aivan — все, для остальных — только свои."""
    player = get_current_player()
    if is_aivan():
        applications = Application.query.order_by(Application.created_at.desc()).all()
    else:
        applications = Application.query.filter_by(player_id=player.id).order_by(Application.created_at.desc()).all()
    levels = {l.id: l for l in AivanLevels.query.all()}
    players = {p.id: p for p in Players.query.all()}
    return render_template(
        'applications.html',
        applications=applications,
        levels=levels,
        players=players,
        is_aivan=is_aivan(),
    )


@applications_bp.route('/applications/new', methods=['GET', 'POST'])
@login_required
def new_application():
    """Подать заявку на добавление прохождения (type=1)."""
    if request.method == 'POST':
        level_id = request.form.get('level_id')
        completion_date_str = (request.form.get('completion_date') or '').strip() or None
        try:
            level_id = int(level_id)
        except (TypeError, ValueError):
            return redirect(url_for('applications.new_application'))
        level = AivanLevels.query.get(level_id)
        if not level:
            return redirect(url_for('applications.new_application'))
        player = get_current_player()
        # Проверка: нет ли уже прохождения у этого игрока на этот уровень
        existing = Completions.query.filter_by(player_id=player.id, level_id=level_id).first()
        if existing:
            return render_template('new_application.html', error='already_completed', levels=AivanLevels.query.order_by(AivanLevels.level_name).all())
        completion_date = None
        if completion_date_str:
            try:
                completion_date = datetime.strptime(completion_date_str, '%Y-%m-%d').date()
            except ValueError:
                pass
        app = Application(
            player_id=player.id,
            type=APPLICATION_TYPE_ADD_COMPLETION,
            status=APPLICATION_STATUS_PENDING,
            created_at=datetime.utcnow(),
            level_id=level_id,
            completion_date=completion_date,
        )
        db.session.add(app)
        db.session.commit()
        return redirect(url_for('applications.list_applications'))
    levels = AivanLevels.query.order_by(AivanLevels.level_name).all()
    return render_template('new_application.html', levels=levels)


@applications_bp.route('/applications/<int:app_id>/status', methods=['POST'])
@login_required
def set_status(app_id):
    """Изменить статус заявки (только Aivan)."""
    if not is_aivan():
        return redirect(url_for('applications.list_applications'))
    app = Application.query.get_or_404(app_id)
    new_status = request.form.get('status')
    try:
        new_status = int(new_status)
    except (TypeError, ValueError):
        return redirect(url_for('applications.list_applications'))
    if new_status not in (APPLICATION_STATUS_PENDING, APPLICATION_STATUS_ACCEPTED, APPLICATION_STATUS_REJECTED, APPLICATION_STATUS_QUESTIONS):
        return redirect(url_for('applications.list_applications'))
    app.status = new_status
    app.updated_at = datetime.utcnow()
    app.notes = request.form.get('notes', app.notes)
    db.session.commit()
    return redirect(url_for('applications.list_applications'))


@applications_bp.route('/applications/<int:app_id>/execute', methods=['POST'])
@login_required
def execute_application(app_id):
    """Выполнить заявку (только Aivan): для type=1 — создать прохождение."""
    if not is_aivan():
        return redirect(url_for('applications.list_applications'))
    app = Application.query.get_or_404(app_id)
    if app.status != APPLICATION_STATUS_PENDING:
        return redirect(url_for('applications.list_applications'))
    if app.type == APPLICATION_TYPE_ADD_COMPLETION and app.level_id:
        existing = Completions.query.filter_by(player_id=app.player_id, level_id=app.level_id).first()
        if not existing:
            compl_date = app.completion_date or date.today()
            c = Completions(
                level_id=app.level_id,
                player_id=app.player_id,
                completion_date=compl_date,
            )
            db.session.add(c)
        app.status = APPLICATION_STATUS_ACCEPTED
        app.updated_at = datetime.utcnow()
        db.session.commit()
    return redirect(url_for('applications.list_applications'))
