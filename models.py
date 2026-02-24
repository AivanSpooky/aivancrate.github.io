"""Database models for AivanCrate."""
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import Table

db = SQLAlchemy()


class AivanExtremes(db.Model):
    __tablename__ = 'aivanextremes'
    id = db.Column(db.Integer, primary_key=True)
    top = db.Column(db.Integer, nullable=True)
    level_name = db.Column(db.String, nullable=True)
    creator_name = db.Column(db.String, nullable=True)
    img = db.Column(db.String, nullable=True)
    attempts = db.Column(db.String, nullable=True)
    device = db.Column(db.String, nullable=True)
    fps = db.Column(db.String, nullable=True)
    opinion = db.Column(db.Text, nullable=True)
    completion = db.Column(db.String, nullable=True)  # YouTube link
    enjoyment = db.Column(db.Numeric(4, 2), nullable=True)  # 0–10
    compl_date = db.Column(db.Date, nullable=True)

    def __repr__(self):
        return '<AivanExtremes %r>' % self.id


class Genres(db.Model):
    __tablename__ = 'genres'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String, nullable=True)
    img_url = db.Column(db.String, nullable=True)

    def __repr__(self):
        return '<Genres %r>' % self.id


level_genres = db.Table(
    'level_genres',
    db.Column('id', db.Integer, primary_key=True),
    db.Column('level_id', db.Integer, db.ForeignKey('aivanlevels.id'), nullable=False),
    db.Column('genre_id', db.Integer, db.ForeignKey('genres.id'), nullable=False)
)


class AivanLevels(db.Model):
    __tablename__ = 'aivanlevels'
    id = db.Column(db.Integer, primary_key=True)
    top = db.Column(db.Integer, nullable=True)
    top_diff = db.Column(db.Integer, nullable=True)
    level_name = db.Column(db.String, nullable=True)
    creator_name = db.Column(db.String, nullable=True)
    img = db.Column(db.String, nullable=True)
    difficulty = db.Column(db.Integer, nullable=True)
    state = db.Column(db.String, nullable=True)
    level_id = db.Column(db.Integer, nullable=True)
    points = db.Column(db.Integer, nullable=True)
    song_replacement = db.Column(db.Boolean, default=False)
    creation_date = db.Column(db.Date, nullable=True)  # дата создания уровня для годовой статистики
    completions = db.relationship('Completions', backref='level', lazy=True)
    genres = db.relationship(
        'Genres',
        secondary=level_genres,
        backref=db.backref('levels', lazy=True)
    )

    def __repr__(self):
        return '<AivanLevels %r>' % self.id


class Players(db.Model):
    __tablename__ = 'players'
    id = db.Column(db.Integer, primary_key=True)
    nickname = db.Column(db.String, nullable=True)
    version = db.Column(db.String, nullable=True)
    icon = db.Column(db.String, nullable=True)
    display_this = db.Column(db.Boolean, default=True)
    password_hash = db.Column(db.String(255), nullable=True)  # хеш пароля для входа
    completions = db.relationship('Completions', backref='player', lazy=True)
    applications = db.relationship('Application', backref='player', lazy=True, foreign_keys='Application.player_id')

    def __repr__(self):
        return '<Players %r>' % self.id


# Типы заявок: 1 — добавление прохождения
APPLICATION_TYPE_ADD_COMPLETION = 1

# Статусы заявки: 1 — в ожидании, 2 — принята, 3 — отменена, 4 — есть вопросы
APPLICATION_STATUS_PENDING = 1
APPLICATION_STATUS_ACCEPTED = 2
APPLICATION_STATUS_REJECTED = 3
APPLICATION_STATUS_QUESTIONS = 4


class Application(db.Model):
    """Общая таблица заявок: игрок, тип, статус, даты, комментарий админа. Детали по типу — в отдельных таблицах."""
    __tablename__ = 'applications'
    id = db.Column(db.Integer, primary_key=True)
    player_id = db.Column(db.Integer, db.ForeignKey('players.id'), nullable=False)
    type = db.Column(db.Integer, nullable=False)
    status = db.Column(db.Integer, nullable=False, default=APPLICATION_STATUS_PENDING)
    created_at = db.Column(db.DateTime, nullable=False)
    updated_at = db.Column(db.DateTime, nullable=True)
    notes = db.Column(db.Text, nullable=True)  # комментарий Aivan (можно менять в любой момент)

    def __repr__(self):
        return '<Application %r>' % self.id


class ApCompletion(db.Model):
    """Заявка на добавление прохождения: уровень, игрок, дата, время (опц.), ссылка на видео (опц.), комментарий."""
    __tablename__ = 'ap_completions'
    id = db.Column(db.Integer, primary_key=True)
    application_id = db.Column(db.Integer, db.ForeignKey('applications.id'), nullable=False, unique=True)
    level_id = db.Column(db.Integer, db.ForeignKey('aivanlevels.id'), nullable=False)
    player_id = db.Column(db.Integer, db.ForeignKey('players.id'), nullable=False)
    completion_date = db.Column(db.Date, nullable=True)
    completion_time = db.Column(db.Time, nullable=True)  # опционально
    video_url = db.Column(db.String(512), nullable=False, default='')  # опционально (в форме); в БД храним ''
    comment = db.Column(db.Text, nullable=True)  # комментарий заявителя

    application = db.relationship('Application', backref=db.backref('ap_completion', uselist=False), foreign_keys=[application_id])
    level = db.relationship('AivanLevels', backref='ap_completions', foreign_keys=[level_id])
    player = db.relationship('Players', backref='ap_completions', foreign_keys=[player_id])

    def __repr__(self):
        return '<ApCompletion %r>' % self.id


class Completions(db.Model):
    __tablename__ = 'completions'
    id = db.Column(db.Integer, primary_key=True)
    level_id = db.Column(db.Integer, db.ForeignKey('aivanlevels.id'), nullable=False)
    player_id = db.Column(db.Integer, db.ForeignKey('players.id'), nullable=False)
    completion_date = db.Column(db.Date, nullable=True)
    completion_time = db.Column(db.Time, nullable=True)  # для однозначного порядка при одной дате (не выводится в UI)

    def __repr__(self):
        return '<Completions %r>' % self.id


class ReplacementSongs(db.Model):
    __tablename__ = 'replacementsongs'
    id = db.Column(db.Integer, primary_key=True)
    song_name = db.Column(db.String, nullable=True)
    author_name = db.Column(db.String, nullable=True)
    link = db.Column(db.String, nullable=True)
    level_id = db.Column(db.Integer, db.ForeignKey('aivanlevels.id'), nullable=True)

    def __repr__(self):
        return '<ReplacementSongs %r>' % self.id


class Rules(db.Model):
    __tablename__ = 'rules'
    id = db.Column(db.Integer, primary_key=True)
    rule_prio = db.Column(db.Integer, nullable=False)
    rule_number = db.Column(db.Integer, nullable=False)
    rule_desc_ru = db.Column(db.Text, nullable=False)
    rule_desc_en = db.Column(db.Text, nullable=False)

    def __repr__(self):
        return '<Rules %r>' % self.id
