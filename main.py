"""AivanCrate - Flask application entry point."""
import os
from flask import Flask, request, g, make_response
from models import db
from i18n import get_translations, get_lang_from_request

from models import (
    AivanExtremes, Genres, AivanLevels, Players, Completions,
    ReplacementSongs, Rules
)

from routes.levels import levels_bp
from routes.extremes import extremes_bp
from routes.top import top_bp
from routes.other import other_bp
from routes.auth import auth_bp
from routes.applications import applications_bp


def create_app():
    app = Flask(__name__)
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///aivancrate.db'
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-secret-change-in-production')

    db.init_app(app)

    app.register_blueprint(levels_bp)
    app.register_blueprint(extremes_bp)
    app.register_blueprint(top_bp)
    app.register_blueprint(other_bp)
    app.register_blueprint(auth_bp, url_prefix='')
    app.register_blueprint(applications_bp, url_prefix='')

    @app.before_request
    def set_lang():
        g.lang = get_lang_from_request(request)

    @app.before_request
    def set_current_player():
        from routes.auth import get_current_player
        g.current_player = get_current_player()

    @app.template_filter('truncate_chars')
    def truncate_chars(s, length=50):
        """Обрезает строку до length символов и добавляет '...' если длиннее."""
        if s is None:
            return ''
        s = str(s)
        if len(s) <= length:
            return s
        return s[:length].rstrip() + '...'

    @app.context_processor
    def inject_i18n():
        from urllib.parse import urlencode
        t = get_translations(getattr(g, 'lang', 'ru'))
        lang = getattr(g, 'lang', 'ru')

        def lang_url(l):
            args = request.args.to_dict(flat=False)
            args['lang'] = [l]
            return request.path + '?' + urlencode(args, doseq=True)
        return dict(t=t, lang=lang, lang_url=lang_url, current_player=g.get('current_player'))

    @app.after_request
    def set_lang_cookie(response):
        if request.args.get('lang') and request.args.get('lang') in ('ru', 'en'):
            response.set_cookie('lang', request.args.get('lang'), max_age=60*60*24*365)
        return response

    return app


app = create_app()


@app.cli.command()
def init_db():
    """Create database tables."""
    with app.app_context():
        db.create_all()
        print('Database initialized.')


if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        for mod in ('migrate_extremes', 'migrate_completions_time', 'migrate_levels_creation_date', 'migrate_auth_applications'):
            try:
                __import__(mod).migrate()
            except Exception as e:
                print(f"Migration {mod}: {e}")
    app.run(debug=True)
