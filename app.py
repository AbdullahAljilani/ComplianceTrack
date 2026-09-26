"""ComplianceTrack application entry point.

Layered architecture as designed in Unit 3: a browser presentation layer, a
Flask application layer holding the feature modules, shared Authentication /
Authorization and Audit Logging services that every module calls, and a
PostgreSQL data layer reached only through src.db.

Unit 5 scope: all four modules are implemented. Unit 4 shipped the Control
Register and the Reporting Dashboard; Unit 5 adds Evidence Management and the
Remediation Tracker, and moves the dashboard onto the scoring service.
"""
from flask import Flask, render_template
from flask_wtf.csrf import CSRFProtect

from config import Config
from src import db
from src.control_register import routes as control_routes
from src.evidence_management import routes as evidence_routes
from src.remediation_tracker import routes as remediation_routes
from src.reporting_dashboard import routes as dashboard_routes
from src.services import auth
from src.services import auth_routes

csrf = CSRFProtect()


def create_app(config_object=Config):
    app = Flask(__name__)
    app.config.from_object(config_object)
    app.config["DB_SETTINGS"] = config_object.DB

    csrf.init_app(app)

    app.teardown_appcontext(db.close_conn)
    app.before_request(auth.load_user_into_g)

    app.register_blueprint(auth_routes.bp)
    app.register_blueprint(dashboard_routes.bp)
    app.register_blueprint(control_routes.bp)
    app.register_blueprint(evidence_routes.bp)
    app.register_blueprint(remediation_routes.bp)

    @app.context_processor
    def inject_user():
        return {"current_user": auth.current_user(), "can": auth.has_permission}

    @app.errorhandler(404)
    def not_found(_):
        return render_template("404.html"), 404


    @app.after_request
    def security_headers(resp):
        resp.headers.setdefault("X-Content-Type-Options", "nosniff")
        resp.headers.setdefault("X-Frame-Options", "DENY")
        resp.headers.setdefault("Referrer-Policy", "same-origin")
        resp.headers.setdefault(
            "Content-Security-Policy",
            "default-src 'self'; img-src 'self' data:; style-src 'self'",
        )
        return resp

    return app


app = create_app()


if __name__ == "__main__":
    with app.app_context():
        try:
            name, version = db.healthcheck()
            print(f"  database : {name} ({version})")
        except Exception as exc:                       # fail loudly, not silently
            raise SystemExit(
                f"\n  Cannot reach the database: {exc}\n"
                f"  Check the DB_* values in your .env file.\n"
            )
    print("  ComplianceTrack running at http://127.0.0.1:5000")
    app.run(debug=True, host="127.0.0.1", port=5000)
