"""Routes for main, about, rules, contacts, pass, create extremes."""
from flask import Blueprint, redirect, render_template, request, url_for, jsonify
from models import db, Rules, AivanExtremes

other_bp = Blueprint('other', __name__)


@other_bp.route('/')
def index():
    return render_template('main.html')


@other_bp.route('/pass', methods=['POST', 'GET'])
def passw():
    if request.method == 'POST':
        passwo = request.form.get('passwo', '')
        is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
        if passwo == '95877':
            if is_ajax:
                return jsonify({'success': True, 'redirect': '/ax'})
            return redirect('/ax')
        if is_ajax:
            return jsonify({'success': False})
        return render_template('cr_pass.html', notpas=True)
    return render_template('cr_pass.html', notpas=False)


@other_bp.route('/aboutaivan')
def aboutaivan():
    return render_template('aboutaivan.html')


@other_bp.route('/rules')
def rules():
    all_rules = Rules.query.order_by(Rules.rule_prio.asc(), Rules.rule_number.asc()).all()
    grrules = {}
    for rule in all_rules:
        if rule.rule_prio not in grrules:
            grrules[rule.rule_prio] = []
        grrules[rule.rule_prio].append(rule)
    sorted_prios = sorted(grrules.keys())
    return render_template('rules.html', grlst=grrules, sorted_prios=sorted_prios)


@other_bp.route('/ax', methods=['POST', 'GET'])
def create_ax():
    if request.method == 'POST':
        level_name = request.form.get('level_name', '')
        creator_name = request.form.get('creator_name', '')
        img = request.form.get('img', '')
        attempts = request.form.get('attempts', '')
        device = request.form.get('device', '')
        fps = request.form.get('fps', '')
        opinion = request.form.get('opinion', '')
        completion = request.form.get('completion', '').strip() or None
        enjoyment_raw = request.form.get('enjoyment', '')
        compl_date_raw = request.form.get('compl_date', '').strip() or None

        enjoyment = None
        if enjoyment_raw:
            try:
                v = float(enjoyment_raw)
                enjoyment = min(10, max(0, round(v, 2))) if 0 <= v <= 10 else None
            except (ValueError, TypeError):
                pass

        compl_date = None
        if compl_date_raw:
            from datetime import datetime
            try:
                compl_date = datetime.strptime(compl_date_raw, '%Y-%m-%d').date()
            except ValueError:
                pass

        article = AivanExtremes(
            level_name=level_name,
            creator_name=creator_name,
            img=img,
            attempts=attempts,
            device=device,
            fps=fps,
            opinion=opinion,
            completion=completion,
            enjoyment=enjoyment,
            compl_date=compl_date,
        )
        try:
            db.session.add(article)
            db.session.commit()
            return redirect('/')
        except Exception:
            return 'Ошибка заполнения данных'
    return render_template('create_ax.html')


@other_bp.route('/contacts')
def contacts():
    return render_template('contacts.html')
