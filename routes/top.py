"""Routes for leaderboards and player profile."""
from datetime import time
from flask import Blueprint, render_template, request
from sqlalchemy import func
from models import db, Players, Completions, AivanLevels
from services.level_service import levels_by_creator_nickname

top_bp = Blueprint('top', __name__)

PER_PAGE_OPTIONS = [10, 25, 50, 0]
TOP_COMPLETIONS_SHOW = 5  # на странице топа показывать только первые 5 по сложности

DIFFICULTY_OPTIONS = [
    ('', 'All'),
    (1, 'Extreme Demon'),
    (2, 'Insane Demon'),
    (3, 'Hard Demon'),
    (4, 'Medium Demon'),
    (5, 'Easy Demon'),
    (6, 'Insane'),
    (7, 'Harder'),
    (8, 'Hard'),
    (9, 'Normal'),
    (10, 'Easy'),
]


def _build_player_data(players, difficulty_filter=None):
    """Строит список игроков с completions (от сложного к лёгкому). difficulty_filter — только уровни этой сложности."""
    data = []
    for player in players:
        completions = Completions.query.filter_by(player_id=player.id).all()
        level_ids = [c.level_id for c in completions]
        completed_levels = AivanLevels.query.filter(
            AivanLevels.id.in_(level_ids)
        ).order_by(AivanLevels.top_diff.asc()).all()
        if difficulty_filter is not None:
            try:
                diff_int = int(difficulty_filter)
                completed_levels = [l for l in completed_levels if l.difficulty == diff_int]
            except (ValueError, TypeError):
                pass
        total_points = (
            db.session.query(func.sum(AivanLevels.points))
            .filter(AivanLevels.id.in_(level_ids))
            .scalar()
        ) or 0
        all_completions = [
            {
                'level_id': level.id,
                'diff': level.difficulty,
                'text': f"{level.level_name} by {level.creator_name}",
            }
            for level in completed_levels
        ]
        data.append({
            'player': player,
            'all_completions': all_completions,
            'total_points': total_points,
        })
    data.sort(key=lambda x: x['total_points'], reverse=True)
    return data


def _assign_ranks_and_peers(data):
    """Присваивает ранг с учётом ничьих (одинаковые очки = одно место) и список rank_peers."""
    rank = 1
    for i, row in enumerate(data):
        if i > 0 and row['total_points'] != data[i - 1]['total_points']:
            rank = i + 1
        row['rank'] = rank
    rank_to_peers = {}
    for row in data:
        r = row['rank']
        if r not in rank_to_peers:
            rank_to_peers[r] = []
        rank_to_peers[r].append(row['player'])
    for row in data:
        row['rank_peers'] = rank_to_peers[row['rank']]
    return data


@top_bp.route('/top')
def top():
    """Leaderboards with pagination and difficulty filter."""
    page = request.args.get('page', 1)
    per_page_arg = request.args.get('per_page', '10')
    difficulty_filter = request.args.get('difficulty', '').strip() or None
    if difficulty_filter == '':
        difficulty_filter = None

    try:
        per_page = int(per_page_arg)
    except (TypeError, ValueError):
        per_page = 10

    players = Players.query.filter_by(display_this=True).all()
    data = _build_player_data(players, difficulty_filter)
    data = _assign_ranks_and_peers(data)

    total = len(data)
    current_per_page = per_page  # для шаблона и URL: 0 = «Все»
    effective_per_page = max(total, 1) if per_page <= 0 else per_page
    if per_page <= 0:
        page = 1
    try:
        page = max(1, int(page))
    except (TypeError, ValueError):
        page = 1
    pages = (total + effective_per_page - 1) // effective_per_page if effective_per_page > 0 else 1
    page = min(page, pages) if pages > 0 else 1
    start = (page - 1) * effective_per_page
    end = start + effective_per_page
    paginated_data = data[start:end]
    pagination = type('Pagination', (), {
        'items': paginated_data,
        'page': page,
        'pages': pages,
        'total': total,
        'per_page': effective_per_page,
    })()

    return render_template(
        'top.html',
        data=pagination.items,
        pagination=pagination,
        per_page_options=PER_PAGE_OPTIONS,
        current_per_page=current_per_page,
        difficulty_options=DIFFICULTY_OPTIONS,
        current_difficulty=difficulty_filter,
        top_completions_show=TOP_COMPLETIONS_SHOW,
    )


@top_bp.route('/player/<int:player_id>')
def player_profile(player_id):
    """Профиль игрока: левая часть — кубик, ник, место; правая — достижения. Спецстраница для Aivan (id=1), плейсхолдер для несуществующих/скрытых."""
    if player_id == 1:
        return render_template('player_aivan_placeholder.html')

    player = Players.query.get(player_id)
    if not player or not player.display_this:
        return render_template('player_unavailable.html'), 404

    difficulty_filter = request.args.get('difficulty', '').strip() or None
    if difficulty_filter == '':
        difficulty_filter = None

    # Ранг считаем по полному топу (без фильтра по сложности), с учётом ничьих
    all_players = Players.query.filter_by(display_this=True).all()
    data_full = _build_player_data(all_players, difficulty_filter=None)
    data_full = _assign_ranks_and_peers(data_full)
    rank = None
    rank_peers = []
    for row in data_full:
        if row['player'].id == player.id:
            rank = row['rank']
            rank_peers = row['rank_peers']
            break

    # Достижения для отображения (с опциональным фильтром по сложности)
    data_filtered = _build_player_data([player], difficulty_filter)
    completions = data_filtered[0]['all_completions'] if data_filtered else []

    time_nulls_last = func.coalesce(Completions.completion_time, time(23, 59, 59))

    # Уровни, которые этот игрок верифнул (первый по дате прохождения = Verification)
    verifier_level_ids = set()
    for comp in completions:
        level_id = comp.get('level_id')
        if not level_id:
            continue
        first_c = (
            Completions.query.filter_by(level_id=level_id)
            .order_by(Completions.completion_date.asc(), time_nulls_last.asc())
            .first()
        )
        if first_c and first_c.player_id == player.id:
            verifier_level_ids.add(level_id)

    # First victor: уровень, где игрок второй по счёту (индекс 1)
    first_victor_level_ids = set()
    for comp in completions:
        level_id = comp.get('level_id')
        if not level_id:
            continue
        ordered = (
            Completions.query.filter_by(level_id=level_id)
            .order_by(Completions.completion_date.asc(), time_nulls_last.asc())
            .limit(2)
            .all()
        )
        if len(ordered) >= 2 and ordered[1].player_id == player.id:
            first_victor_level_ids.add(level_id)

    # First completed level: самое раннее прохождение игрока по дате
    first_completed = (
        Completions.query.filter_by(player_id=player.id)
        .order_by(Completions.completion_date.asc(), time_nulls_last.asc())
        .first()
    )
    first_completed_level_id = first_completed.level_id if first_completed else None

    creator_levels = levels_by_creator_nickname(player.nickname)

    from flask import g
    current = g.get('current_player')
    is_self = current is not None and current.id == player.id

    return render_template(
        'player_profile.html',
        player=player,
        rank=rank,
        rank_peers=rank_peers,
        completions=completions,
        creator_levels=creator_levels,
        verifier_level_ids=verifier_level_ids,
        first_victor_level_ids=first_victor_level_ids,
        first_completed_level_id=first_completed_level_id,
        difficulty_options=DIFFICULTY_OPTIONS,
        current_difficulty=difficulty_filter,
        is_self=is_self,
    )
