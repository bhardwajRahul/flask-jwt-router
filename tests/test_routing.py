"""
    Unit Tests for:
        - Routing class: that deal with encoding & decoding tokens & authorising routes.
        - Entity class: This covers the get_id_from_token method.

    Config values used in routing:

    "WHITE_LIST_ROUTES" = [("PUT", "/banana")]
    "IGNORED_ROUTES" = [("GET", "/")]
    "JWT_ROUTER_API_NAME" = "/api/v1"
"""
from flask import Flask
from typing import Any
import pytest

from flask_jwt_router._routing import Routing
from flask_jwt_router._config import Config
from flask_jwt_router._entity import Entity
from flask_jwt_router.oauth2.google import Google
from tests.fixtures.token_fixture import mock_token, mock_access_token
from tests.fixtures.model_fixtures import TestMockEntity, MockAOuthModel
from tests.fixtures.app_fixtures import jwt_router_client, test_client_static
from tests.fixtures.main_fixture import test_client
from tests.fixtures.oauth_fixtures import http_requests, oauth_urls


class MockArgs:
    def __init__(self, token=None, headers=None):
        self.token = token
        self.headers = headers

    def get(self, t):
        if t == "X-Auth-Token":
            return f"Bearer {self.token}"
        if self.headers:
            return f"Bearer {self.token}"
        else:
            return self.token


class TestRouting:

    app = None
    app_config = {
        "WHITE_LIST_ROUTES": [("PUT", "/banana")],
        "IGNORED_ROUTES": [("GET", "/")],
        "JWT_ROUTER_API_NAME": "/api/v1",
        "SECRET_KEY": "__TEST_SECRET__",
    }
    oauth_options = {
        "client_id": "<CLIENT_ID>",
        "client_secret": "<CLIENT_SECRET>",
        "redirect_uri": "http://localhost:3000",
        "tablename": "oauth_tablename",
        "email_field": "email",
        "expires_in": 3600,
    }

    def test_before_middleware(self, monkeypatch, TestMockEntity, MockAOuthModel, mock_token, http_requests):
        app = Flask(__name__)

        @app.route("/test", methods=["GET"])
        def fc_one():
            return "/test"
        # Manually set the primary key
        entity = TestMockEntity(id=1, user_name="joe")
        oauth_entity = MockAOuthModel(id=1, email="jaco@gmail.com")

        ctx = app.test_request_context("/test")
        ctx.push()

        assert entity.user_name == "joe"
        assert entity.id == 1
        assert oauth_entity.id == 1
        assert oauth_entity.email == "jaco@gmail.com"

        config = Config()
        config.init_config(self.app_config, google_oauth=self.oauth_options)

        config.entity_models = [TestMockEntity, MockAOuthModel]
        entity = Entity(config)
        google = Google(http_requests(oauth_urls))
        google.init(**config.google_oauth)
        routing = Routing(app, config, entity, google)

        with ctx:
            # token from args
            monkeypatch.setattr("flask.request.args", MockArgs(mock_token))
            routing.before_middleware()
            assert ctx.g.test_entities == [(1, 'joe')]

        with ctx:
            # token from headers
            monkeypatch.setattr("flask.request.args", MockArgs())
            monkeypatch.setattr("flask.request.headers", MockArgs(mock_token, True))
            routing.before_middleware()
            assert ctx.g.test_entities == [(1, 'joe')]

        with ctx:
            # token from oauth headers
            monkeypatch.setattr("flask.request.headers", MockArgs("<access_token>", "X-Auth-Token"))
            routing.before_middleware()
            assert ctx.g.oauth_tablename == [(1, "jaco@gmail.com")]

    @pytest.mark.parametrize(
        "jwt_router_client,entity_model,expected", [
            ({"WHITE_LIST_ROUTES": [("GET", "/test")]}, None, "200"),
            ({"WHITE_LIST_ROUTES": []}, None, "401"),
            ({"WHITE_LIST_ROUTES": [("POST", "/test")]}, None, "401"),
            ({}, None, "401"),
        ], indirect=["jwt_router_client"]
    )
    def test_jwt_route(self, jwt_router_client, entity_model, expected):
        rv = jwt_router_client.get("/test")
        assert expected in str(rv.status)

    def test_api_named_routes(self, test_client):
        rv = test_client.get("/api/v1/test")
        assert "200" in str(rv.status)

    def test_sub_paths(self, test_client):
        rv = test_client.get("/api/v1/bananas/sub")
        assert "200" in str(rv.status)
        assert rv.get_json()["data"] == "sub"

        rv = test_client.get("/api/v1/test/sub_two")
        assert "401" in str(rv.status)

    def test_dynamic_params(self, test_client):
        rv = test_client.put("/api/v1/apples/sub/1")
        assert "200" in str(rv.status)

        rv = test_client.get("/api/v1/apples/sub/")
        assert "404" in str(rv.status)

        rv = test_client.get("/api/v1/apples/sub/hello")
        assert "404" in str(rv.status)

    def test_static_routes(self, test_client):
        """
        Tests if the static path is handled both by default and
        if the path is past to the static_folder kwarg
        """
        rv = test_client.get("/static/images/Group.jpg")
        assert "200" in str(rv.status)

        rv = test_client.get("/")
        assert "200" in str(rv.status)

    def test_static_client(self, test_client_static):
        rv = test_client_static.get("/static_copy/images/Group.jpg")
        assert "200" in str(rv.status)

    def test_ignored_routes(self, test_client):
        rv = test_client.get("/ignore")
        assert "200" in str(rv.status)

    def test_ignored_route_path(self, test_client):
        rv = test_client.get("/")
        assert "200" in str(rv.status)

    def test_handle_pre_flight_request(self, test_client):
        rv = test_client.options("/")
        assert "200" in str(rv.status)
