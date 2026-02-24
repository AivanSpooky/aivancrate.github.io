"""Authentication: login, logout, change password."""
from flask import Blueprint, render_template, request, redirect, url_for, session, g
from werkzeug.security import check_password_hash, generate_password_hash
from models import Players
from functools import wraps

auth_bp = Blueprint('auth', __name__)

AIVAN_PLAYER_ID = 1


def login_required(f):
    """Декоратор: только для авторизованных игроков."""
    @wraps(f)
    def wrapped(*args, **kwargs):
        if 'player_id' not in session:
            return redirect(url_for('auth.login', next=request.url))
        return f(*args, **kwargs)
    return wrapped


def get_current_player():
    """Текущий игрок из сессии или None."""
    if 'player_id' not in session:
        return None
    return Players.query.get(session['player_id'])


def is_aivan():
    """Является ли текущий пользователь Aivan (id=1)."""
    return session.get('player_id') == AIVAN_PLAYER_ID


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        nickname = (request.form.get('nickname') or '').strip()
        password = request.form.get('password') or ''
        next_url = request.args.get('next') or url_for('other.index')
        if not nickname:
            return render_template('login.html', error='auth_enter_nickname', next=next_url)
        player = Players.query.filter(Players.nickname.ilike(nickname)).first()
        if not player:
            return render_template('login.html', error='auth_unknown_user', next=next_url)
        if not player.password_hash:
            return render_template('login.html', error='auth_no_password', next=next_url)
        if not check_password_hash(player.password_hash, password):
            return render_template('login.html', error='auth_bad_password', next=next_url)
        session['player_id'] = player.id
        session.permanent = True
        return redirect(next_url)
    next_url = request.args.get('next') or url_for('other.index')
    return render_template('login.html', next=next_url)


@auth_bp.route('/logout')
def logout():
    session.pop('player_id', None)
    return redirect(request.referrer or url_for('other.index'))


@auth_bp.route('/account/change-password', methods=['GET', 'POST'])
@login_required
def change_password():
    player = get_current_player()
    if not player:
        return redirect(url_for('auth.login'))
    if request.method == 'POST':
        current = request.form.get('current_password') or ''
        new_pass = request.form.get('new_password') or ''
        new_pass2 = request.form.get('new_password2') or ''
        if not current:
            return render_template('change_password.html', error='auth_enter_current')
        if not player.password_hash or not check_password_hash(player.password_hash, current):
            return render_template('change_password.html', error='auth_wrong_current')
        if not new_pass or len(new_pass) < 6:
            return render_template('change_password.html', error='auth_password_short')
        if new_pass != new_pass2:
            return render_template('change_password.html', error='auth_password_mismatch')
        player.password_hash = generate_password_hash(new_pass, method='pbkdf2:sha256')
        from models import db
        db.session.commit()
        return redirect(url_for('applications.list_applications'))
    return render_template('change_password.html')
