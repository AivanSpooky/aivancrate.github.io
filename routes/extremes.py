"""Routes for Aivan's completed extremes."""
import re
from flask import Blueprint, render_template, request
from sqlalchemy import extract
from models import AivanExtremes
from services.level_service import paginate_query, find_level_by_name, aivanlevels_name_set_for_tag

extremes_bp = Blueprint('extremes', __name__)

PER_PAGE_OPTIONS = [10, 25, 50, 0]

YT_PATTERNS = [
    r'(?:youtube\.com/watch\?v=|youtu\.be/|youtube\.com/embed/)([a-zA-Z0-9_-]{11})',
]


def extract_youtube_id(url):
    if not url:
        return None
    for pat in YT_PATTERNS:
        m = re.search(pat, url)
        if m:
            return m.group(1)
    return None


def _img_src(img_value):
    """URL для превью: из БД без изменений, но относительный путь делаем от корня сайта."""
    if not img_value:
        return ''
    s = (img_value or '').strip()
    if s.startswith('http://') or s.startswith('https://'):
        return s
    return '/' + s.lstrip('/')


@extremes_bp.route('/extreme/<int:extreme_id>')
def extreme_detail(extreme_id):
    """Detail page for a single extreme completion (YouTube-like layout)."""
    extreme = AivanExtremes.query.get_or_404(extreme_id)
    yt_id = extract_youtube_id(extreme.completion) if extreme.completion else None
    aivan_level = find_level_by_name(extreme.level_name) if extreme.level_name else None
    return render_template(
        'extreme_detail.html',
        extreme=extreme,
        img_src=_img_src(extreme.img),
        yt_id=yt_id,
        aivan_level=aivan_level,
    )


def _normalize_level_name(name):
    if not name:
        return ''
    return ' '.join((name or '').strip().split()).lower()


@extremes_bp.route('/aivanextremes')
def extremes():
    """Extreme demons list with pagination, sort and tags."""
    page = request.args.get('page', 1)
    per_page_arg = request.args.get('per_page', '10')
    sort = request.args.get('sort', 'difficulty')
    try:
        per_page = int(per_page_arg)
    except (TypeError, ValueError):
        per_page = 10

    if sort == 'enjoyment':
        from sqlalchemy import func
        query = AivanExtremes.query.order_by(
            func.coalesce(AivanExtremes.enjoyment, -1).desc(),
            AivanExtremes.top.asc()
        )
    else:
        query = AivanExtremes.query.order_by(AivanExtremes.top.asc())
    pagination = paginate_query(query, page, per_page)

    aivan_names = aivanlevels_name_set_for_tag()
    for el in pagination.items:
        el.in_aivanlevels = _normalize_level_name(el.level_name) in aivan_names
        el.img_src = _img_src(el.img)

    return render_template(
        'aivanextremes.html',
        articles=pagination.items,
        pagination=pagination,
        per_page_options=PER_PAGE_OPTIONS,
        current_per_page=per_page,
        current_sort=sort,
    )


@extremes_bp.route('/aivanextremes/yearly')
def extremes_yearly_index():
    """Список годов для годовой статистики (редирект на первый год или список)."""
    from flask import redirect, url_for
    years = [
        r[0] for r in
        AivanExtremes.query.with_entities(
            extract('year', AivanExtremes.compl_date).label('y')
        ).filter(AivanExtremes.compl_date.isnot(None)).distinct().order_by('y').all()
    ]
    if not years:
        return render_template('extremes_yearly.html', year=None, years=[], articles=[], count=0)
    return redirect(url_for('extremes.extremes_by_year', year=years[0]))


@extremes_bp.route('/aivanextremes/yearly/<int:year>')
def extremes_by_year(year):
    """Прохождения за конкретный год, отсортированные по дате (от ранних к поздним)."""
    articles = (
        AivanExtremes.query.filter(
            extract('year', AivanExtremes.compl_date) == year
        )
        .order_by(AivanExtremes.compl_date.asc(), AivanExtremes.id.asc())
        .all()
    )
    years = [
        r[0] for r in
        AivanExtremes.query.with_entities(
            extract('year', AivanExtremes.compl_date).label('y')
        ).filter(AivanExtremes.compl_date.isnot(None)).distinct().order_by('y').all()
    ]
    aivan_names = aivanlevels_name_set_for_tag()
    for el in articles:
        el.in_aivanlevels = _normalize_level_name(el.level_name) in aivan_names
        el.img_src = _img_src(el.img)
    return render_template(
        'extremes_yearly.html',
        year=year,
        years=years,
        articles=articles,
        count=len(articles),
    )


@extremes_bp.route('/aivanextremes/time-machine')
def time_machine():
    """Машина времени: таймлайн от первого прохождения до последнего, список топ-N на выбранную дату."""
    items = (
        AivanExtremes.query.filter(AivanExtremes.compl_date.isnot(None))
        .order_by(AivanExtremes.compl_date.asc(), AivanExtremes.id.asc())
        .all()
    )
    aivan_names = aivanlevels_name_set_for_tag()
    data = []
    for el in items:
        data.append({
            'id': el.id,
            'level_name': el.level_name or '',
            'creator_name': el.creator_name or '',
            'compl_date': el.compl_date.isoformat() if el.compl_date else None,
            'top': el.top,
            'img_src': _img_src(el.img),
            'in_aivanlevels': _normalize_level_name(el.level_name) in aivan_names,
        })
    from flask import json
    return render_template(
        'time_machine.html',
        timeline_data_json=json.dumps(data),
    )
