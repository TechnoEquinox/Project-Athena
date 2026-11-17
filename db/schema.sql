-- SPDX-License-Identifier: AGPL-3.0-or-later
-- Copyright (C) 2026 Connor Bailey

-- REFERENCE ONLY. The source of truth is the SQLAlchemy models + Alembic migrations in api/.
-- Defines the schema for a tech that takes appointments with clients.
CREATE TABLE tech (
    tech_id integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    first_name text NOT NULL,
    last_name text NOT NULL,
    start_date date NOT NULL,
    is_active boolean NOT NULL DEFAULT true
);

-- Defines the schema for a client that can make appointments with techs.
CREATE TABLE client (
    client_id integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    first_name text NOT NULL,
    last_name text NOT NULL,
    phone text,
    email text,
    zipcode text,
    languages text[] NOT NULL DEFAULT '{}',
    created_at timestamptz NOT NULL DEFAULT now()
);

-- Defines the schema for a device that a client brings to an appointment with a tech. A client can have multiple devices.
CREATE TABLE client_device (
    device_id integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    client_id integer NOT NULL REFERENCES client(client_id) ON DELETE CASCADE,
    device_type text NOT NULL, -- e.g. phone, tablet, laptop
    description text -- e.g. "iPhone 12 Pro Max", "Samsung Galaxy Tab S7"
);

-- Defines the schema for an appointment between a client and a tech. A client can have multiple appointments with different techs.
CREATE TABLE appointment (
    appointment_id integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    client_id integer NOT NULL REFERENCES client(client_id),
    tech_id integer NOT NULL REFERENCES tech(tech_id),
    appointment_at timestamptz NOT NULL,
    location text NOT NULL,
    length_minutes smallint CHECK (length_minutes > 0),
    notes text,
    created_at timestamptz NOT NULL DEFAULT now()
);

-- Defines the schema for a many-to-many relationship between appointments and devices. An appointment can have multiple devices, and a device can be associated with multiple appointments.
CREATE TABLE appointment_device (
    appointment_id integer NOT NULL REFERENCES appointment(appointment_id) ON DELETE CASCADE,
    device_id integer NOT NULL REFERENCES client_device(device_id),
    PRIMARY KEY (appointment_id, device_id)
);

-- Defines the schema for a call log that records calls made to clients. A call can be associated with a client, but it is not required.
CREATE TABLE call_log (
    call_id integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    client_id integer REFERENCES client(client_id) ON DELETE SET NULL,
    client_first_name text,
    client_last_name text,
    phone text,
    called_at timestamptz NOT NULL DEFAULT now(),
    notes text
);

-- Defines the schema for client feedback on a tech's performance during an appointment. A client can provide feedback for multiple appointments with different techs.
CREATE TABLE client_feedback (
    feedback_id integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tech_id integer NOT NULL REFERENCES tech(tech_id),
    submitted_on date NOT NULL DEFAULT current_date,
    overall_session_rating smallint CHECK (overall_session_rating BETWEEN 1 AND 5),
    tech_knowledge_rating smallint CHECK (tech_knowledge_rating BETWEEN 1 AND 5),
    tech_communication_rating smallint CHECK (tech_communication_rating BETWEEN 1 AND 5),
    tech_friendliness_rating smallint CHECK (tech_friendliness_rating BETWEEN 1 AND 5),
    comments text
);

-- Indexes on fireign keys
CREATE INDEX ON appointment(client_id);
CREATE INDEX ON appointment(tech_id);
CREATE INDEX ON appointment(appointment_at);
CREATE INDEX ON call_log(client_id);
CREATE INDEX ON client_feedback(tech_id);
CREATE INDEX ON client_device(client_id);