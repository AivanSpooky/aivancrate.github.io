"""Routes for Aivan's levels and level detail page."""
from flask import Blueprint, render_template, request, redirect, url_for
from sqlalchemy import extract
from models import AivanLevels, Genres, ReplacementSongs
from services.level_service import (
    query_levels,
    get_level_article,
    paginate_query,
    is_verified_by_in_state,
    find_extreme_by_level_name,
    get_player_by_nickname,
)

levels_bp = Blueprint('levels', __name__)

PER_PAGE_OPTIONS = [10, 25, 50, 0]  # 0 = all


@levels_bp.route('/aivanlevelstop')
def levels_redirect():
    """Redirect old difficulty-sorted URL to unified levels with sort=top_diff."""
    args = request.args.copy()
    args['sort'] = 'top_diff'
    return redirect(url_for('levels.levels', **args))


@levels_bp.route('/aivanlevels')
def levels():
    """Unified levels page with filters, sort, and pagination."""
    name_filter = request.args.get('name', '').strip()
    victor_filter = request.args.get('victor', '').strip()
    diff_filter = request.args.get('difficulty', '')
    genre_filters = request.args.getlist('genre')
    sort_by = request.args.get('sort', 'top_diff')  # 'top' = крутость, 'top_diff' = сложность
    per_page_arg = request.args.get('per_page', '10')
    page = request.args.get('page', 1)

    try:
        per_page = int(per_page_arg)
    except (TypeError, ValueError):
        per_page = 10

    query = query_levels(name_filter, victor_filter, diff_filter, genre_filters, sort_by)
    pagination = paginate_query(query, page, per_page)

    articles = []
    for level in pagination.items:
        articles.append(get_level_article(level))

    all_genres = Genres.query.all()

    return render_template(
        'aivanlevels.html',
        articles=articles,
        all_genres=all_genres,
        pagination=pagination,
        per_page_options=PER_PAGE_OPTIONS,
        current_filters={
            'name': name_filter,
            'victor': victor_filter,
            'difficulty': diff_filter,
            'genre': genre_filters,
            'sort': sort_by,
            'per_page': per_page,
        },
    )


@levels_bp.route('/aivanlevels/yearly')
def levels_yearly_index():
    """Годовая статистика уровней: редирект на первый год с creation_date."""
    years = [
        r[0] for r in
        AivanLevels.query.with_entities(
            extract('year', AivanLevels.creation_date).label('y')
        ).filter(AivanLevels.creation_date.isnot(None)).distinct().order_by('y').all()
    ]
    if not years:
        return render_template('levels_yearly.html', year=None, years=[], levels=[], count=0)
    return redirect(url_for('levels.levels_by_year', year=years[0]))


@levels_bp.route('/aivanlevels/yearly/<int:year>')
def levels_by_year(year):
    """Уровни за конкретный год (по creation_date), от давних к ближайшим."""
    levels = (
        AivanLevels.query.filter(extract('year', AivanLevels.creation_date) == year)
        .order_by(AivanLevels.creation_date.asc(), AivanLevels.id.asc())
        .all()
    )
    years = [
        r[0] for r in
        AivanLevels.query.with_entities(
            extract('year', AivanLevels.creation_date).label('y')
        ).filter(AivanLevels.creation_date.isnot(None)).distinct().order_by('y').all()
    ]
    return render_template(
        'levels_yearly.html',
        year=year,
        years=years,
        levels=levels,
        count=len(levels),
    )


LEVEL_VICTORS_PER_PAGE_DEFAULT = 10
LEVEL_CREATORS_PER_PAGE = 10
VICTORS_PER_PAGE_OPTIONS = [10, 25, 50, 0]  # 0 = all


def _paginate_list(items, page, per_page):
    """Пагинация списка в памяти. per_page=0 — показать все. Возвращает (sliced_items, pagination_dict)."""
    try:
        page = max(1, int(page))
    except (TypeError, ValueError):
        page = 1
    total = len(items)
    effective = max(total, 1) if per_page <= 0 else per_page
    pages = (total + effective - 1) // effective if total else 1
    page = min(page, pages) if pages > 0 else 1
    start = (page - 1) * effective
    end = start + effective
    return items[start:end], {'page': page, 'pages': pages, 'total': total, 'per_page': effective}


@levels_bp.route('/level/<int:level_id>')
def level_detail(level_id):
    """Detail page for a single level (YouTube playlist-like layout)."""
    level = AivanLevels.query.get_or_404(level_id)
    article = get_level_article(level)
    victors_all = article['victors']

    show_verification_tab = (
        is_verified_by_in_state(level.state) and victors_all
    )
    verifier = victors_all[0] if victors_all else None
    verification_extreme = None
    if show_verification_tab and verifier and verifier.get('player_id') == 1:
        verification_extreme = find_extreme_by_level_name(level.level_name)

    # Креаторы: разбиваем creator_name по &, ищем в лидербордах
    creators_in_top = []
    creators_other = []
    if level.creator_name and str(level.creator_name).strip():
        for name in [s.strip() for s in str(level.creator_name).split('&') if s.strip()]:
            player = get_player_by_nickname(name)
            if player:
                creators_in_top.append({
                    'nickname': player.nickname,
                    'icon': player.icon,
                    'player_id': player.id,
                    'in_top': True,
                })
            else:
                creators_other.append({'nickname': name, 'in_top': False})
    creators_combined = creators_in_top + creators_other

    victors_page = request.args.get('victors_page', 1)
    creators_page = request.args.get('creators_page', 1)
    try:
        victors_per_page = int(request.args.get('victors_per_page', LEVEL_VICTORS_PER_PAGE_DEFAULT))
    except (TypeError, ValueError):
        victors_per_page = LEVEL_VICTORS_PER_PAGE_DEFAULT
    if victors_per_page not in VICTORS_PER_PAGE_OPTIONS:
        victors_per_page = LEVEL_VICTORS_PER_PAGE_DEFAULT

    victors_slice, victors_pagination = _paginate_list(
        victors_all, victors_page, victors_per_page
    )
    creators_slice, creators_pagination = _paginate_list(
        creators_combined, creators_page, LEVEL_CREATORS_PER_PAGE
    )

    return render_template(
        'level_detail.html',
        article=article,
        level=level,
        replacement_songs=article['replacement_songs'],
        show_verification_tab=show_verification_tab,
        verifier=verifier,
        verification_extreme=verification_extreme,
        victors=victors_slice,
        victors_pagination=victors_pagination,
        creators=creators_slice,
        creators_pagination=creators_pagination,
        victors_per_page_options=VICTORS_PER_PAGE_OPTIONS,
        current_victors_per_page=victors_per_page,
        victors_per_page=victors_pagination['per_page'],
        creators_per_page=LEVEL_CREATORS_PER_PAGE,
    )
