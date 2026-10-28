from datetime import date, datetime, timezone

import pytest
from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.models import Appointment, Client, ClientFeedback, Tech


def make_tech_and_client():
    tech = Tech(first_name="Connor", last_name="Bailey", start_date=date(2024, 1, 1))
    client = Client(first_name="Test", last_name="Client", languages=["English", "Spanish"])
    db.session.add_all([tech, client])
    db.session.commit()
    return tech, client


def test_create_appointment(app):
    with app.app_context():
        tech, client = make_tech_and_client()
        appt = Appointment(
            client_id=client.client_id,
            tech_id=tech.tech_id,
            appointment_at=datetime.now(timezone.utc),
            location="Library",
            length_minutes=45,
        )
        db.session.add(appt)
        db.session.commit()
        assert appt.appointment_id is not None
        assert client.languages == ["English", "Spanish"]


def test_zero_length_appointment_rejected(app):
    with app.app_context():
        tech, client = make_tech_and_client()
        db.session.add(Appointment(
            client_id=client.client_id, tech_id=tech.tech_id,
            appointment_at=datetime.now(timezone.utc), length_minutes=0,
        ))
        with pytest.raises(IntegrityError):
            db.session.commit()
        db.session.rollback()


def test_appointment_needs_real_client(app):
    with app.app_context():
        tech, _ = make_tech_and_client()
        db.session.add(Appointment(
            client_id=999, tech_id=tech.tech_id, appointment_at=datetime.now(timezone.utc),
        ))
        with pytest.raises(IntegrityError):
            db.session.commit()
        db.session.rollback()


def test_rating_out_of_range_rejected(app):
    with app.app_context():
        tech, _ = make_tech_and_client()
        db.session.add(ClientFeedback(tech_id=tech.tech_id, overall_session_rating=9))
        with pytest.raises(IntegrityError):
            db.session.commit()
        db.session.rollback()


def test_feedback_is_anonymous():
    """Privacy guard: feedback must never link to a client or appointment."""
    columns = {c.name for c in ClientFeedback.__table__.columns}
    assert "client_id" not in columns
    assert "appointment_id" not in columns