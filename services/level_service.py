"""Business logic for level queries and pagination."""
from datetime import time
from sqlalchemy import or_, func
from models import AivanLevels, Genres, Completions, Players, ReplacementSongs


def query_levels(name_filter='', victor_filter='', diff_filter='', genre_filters=None, sort_by='top'):
    """
    Build filtered and sorted query for Aivan levels.
    sort_by: 'top' (крутость/coolness) or 'top_diff' (сложность/difficulty)
    genre_filters: list of genre ids - levels must have ALL selected genres (AND logic)
    """
    query = AivanLevels.query.filter(
        or_(AivanLevels.top.isnot(None), AivanLevels.top_diff.isnot(None))
    )

    if name_filter:
        query = query.filter(AivanLevels.level_name.ilike(f'%{name_filter}%'))

    if victor_filter:
        query = query.filter(
            AivanLevels.completions.any(
                Completions.player.has(Players.nickname.ilike(victor_filter))
            )
        )

    if diff_filter:
        try:
            diff_int = int(diff_filter)
            query = query.filter(AivanLevels.difficulty == diff_int)
        except ValueError:
            pass

    if genre_filters:
        genre_ids = [int(g) for g in genre_filters if g and str(g).isdigit()]
        for gid in genre_ids:
            query = query.filter(AivanLevels.genres.any(Genres.id == gid))

    order_col = AivanLevels.top_diff if sort_by == 'top_diff' else AivanLevels.top
    query = query.order_by(order_col.asc())

    return query


def get_level_article(level):
    """Build article dict for a single level (victors, song, genres)."""
    song = None
    if level.song_replacement:
        songs = ReplacementSongs.query.filter_by(level_id=level.id).all()
        song = songs[0] if songs else None

    # Сначала по дате, затем по времени (NULL времени = конец дня, чтобы верификатор был однозначен)
    time_nulls_last = func.coalesce(Completions.completion_time, time(23, 59, 59))
    completions_query = (
        Completions.query.join(Players, Completions.player_id == Players.id)
        .filter(Completions.level_id == level.id)
        .order_by(Completions.completion_date.asc(), time_nulls_last.asc())
        .all()
    )
    victors = []
    for i, c in enumerate(completions_query):
        player = c.player
        # 1st = Verification, 2nd = First Victor (по порядку в списке)
        is_verification = i == 0
        is_first_victor = i == 1
        victors.append({
            'nickname': player.nickname,
            'icon': player.icon,
            'date': c.completion_date,
            'player_id': player.id,
            'is_verification': is_verification,
            'is_first_victor': is_first_victor,
        })

    return {
        'level': level,
        'song': song,
        'replacement_songs': ReplacementSongs.query.filter_by(level_id=level.id).all(),
        'victors': victors,
        'genres': level.genres,
    }


def is_verified_by_in_state(state):
    """Проверяет, что в статусе уровня есть «verified by»."""
    if not state or not isinstance(state, str):
        return False
    return 'verified by' in state.lower().strip()


def find_extreme_by_level_name(level_name):
    """
    Ищет в aivanextremes запись по имени уровня (совпадение по названию, без учёта регистра).
    Возвращает модель AivanExtremes или None.
    """
    from models import AivanExtremes
    if not level_name or not level_name.strip():
        return None
    name = ' '.join(level_name.strip().split())
    return AivanExtremes.query.filter(AivanExtremes.level_name.ilike(name)).first()


def find_level_by_name(level_name):
    """
    Ищет в aivanlevels запись по имени уровня (совпадение по названию, без учёта регистра).
    Возвращает модель AivanLevels или None.
    """
    if not level_name or not level_name.strip():
        return None
    name = ' '.join(level_name.strip().split())
    return AivanLevels.query.filter(AivanLevels.level_name.ilike(name)).first()


def aivanlevels_name_set():
    """Множество нормализованных названий уровней из aivanlevels (для быстрой проверки)."""
    levels = AivanLevels.query.with_entities(AivanLevels.level_name).filter(
        AivanLevels.level_name.isnot(None)
    ).all()
    return {' '.join((n or '').strip().split()).lower() for (n,) in levels}


def aivanlevels_name_set_for_tag():
    """Множество нормализованных названий уровней из aivanlevels с непустыми top и top_diff (для тега Aivan)."""
    levels = AivanLevels.query.with_entities(AivanLevels.level_name).filter(
        AivanLevels.level_name.isnot(None),
        AivanLevels.top.isnot(None),
        AivanLevels.top_diff.isnot(None),
    ).all()
    return {' '.join((n or '').strip().split()).lower() for (n,) in levels}


def get_player_by_nickname(nickname):
    """Игрок из лидербордов по нику (без учёта регистра). Возвращает Players или None."""
    if not nickname or not str(nickname).strip():
        return None
    nick = str(nickname).strip()
    return Players.query.filter(Players.nickname.ilike(nick)).first()


def levels_by_creator_nickname(nickname):
    """
    Уровни из aivanlevels, в создании которых участвовал игрок.
    creator_name может быть "Aivan&Nkly" — ники через &.
    """
    if not nickname or not nickname.strip():
        return []
    nick = nickname.strip()
    all_levels = AivanLevels.query.filter(
        AivanLevels.creator_name.isnot(None),
        AivanLevels.creator_name != '',
    ).all()
    return [
        level for level in all_levels
        if nick.lower() in [s.strip().lower() for s in (level.creator_name or '').split('&')]
    ]


def paginate_query(query, page, per_page):
    """Apply pagination. per_page=0 means all. Returns object with .items, .page, .pages, .total, .per_page."""
    try:
        page = max(1, int(page))
    except (TypeError, ValueError):
        page = 1
    try:
        per_page = int(per_page) if per_page else 10
    except (TypeError, ValueError):
        per_page = 10

    total = query.count()
    if per_page <= 0:
        per_page = max(total, 1)
        page = 1
    pages = (total + per_page - 1) // per_page if per_page > 0 else 1
    page = min(page, pages) if pages > 0 else 1
    items = query.offset((page - 1) * per_page).limit(per_page).all()
    return type('Pagination', (), {'items': items, 'page': page, 'pages': pages, 'total': total, 'per_page': per_page})()
