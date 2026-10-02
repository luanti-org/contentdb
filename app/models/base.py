# ContentDB
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2018-2025 rubenwardy <rw@rubenwardy>
from typing import TYPE_CHECKING, Any, ClassVar

from flask_migrate import Migrate
from sqlalchemy import Table
from sqlalchemy.orm import Session, scoped_session
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy_searchable import make_searchable

from app import app

# db.session is a scoped_session, which is not a Session subclass
AnySession = Session | scoped_session[Any]

if TYPE_CHECKING:
    from flask_sqlalchemy.model import Model as _FSAModel

    class _SQLAlchemy(SQLAlchemy):
        # Legacy-style relationships are plain instance attributes at runtime, not RelationshipProperty
        def relationship(self, *args: Any, **kwargs: Any) -> Any: ...

    # mypy rejects db.Model as a base class, so expose a statically-known alias.
    class Model(_FSAModel):
        __table__: ClassVar[Table]

    db: _SQLAlchemy = _SQLAlchemy(app)
else:
    db = SQLAlchemy(app)

migrate = Migrate(app, db)
make_searchable(db.metadata)

if not TYPE_CHECKING:
    Model = db.Model
