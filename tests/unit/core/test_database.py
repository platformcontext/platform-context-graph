import os
import pytest
from unittest.mock import MagicMock, patch, call
from platform_context_graph.core.database import DatabaseManager, Neo4jDriverWrapper


class TestDatabaseManager:
    """
    Unit tests for the DatabaseManager class.
    Mocks the actual Neo4j driver to test logic without a real DB.
    """

    @pytest.fixture
    def mock_driver(self):
        with patch("neo4j.GraphDatabase.driver") as mock_driver_cls:
            mock_instance = MagicMock()
            mock_driver_cls.return_value = mock_instance
            yield mock_instance

    def test_initialization(self, mock_driver):
        """Test that DatabaseManager initializes with correct config from env."""
        with patch.dict(
            os.environ,
            {
                "NEO4J_URI": "bolt://localhost:7687",
                "NEO4J_USERNAME": "neo4j",
                "NEO4J_PASSWORD": "password",
            },
        ):
            # Reset properties if singleton already exists (hacky for singleton testing)
            if DatabaseManager._instance:
                DatabaseManager._instance = None

            db_manager = DatabaseManager()
            assert db_manager.neo4j_uri == "bolt://localhost:7687"
            assert db_manager.neo4j_username == "neo4j"

    def test_verify_connection_success(self, mock_driver):
        """Test verify_connectivity returns True on success."""
        with patch.dict(
            os.environ,
            {
                "NEO4J_URI": "bolt://localhost:7687",
                "NEO4J_USERNAME": "u",
                "NEO4J_PASSWORD": "p",
            },
        ):
            # Force re-init
            if DatabaseManager._instance:
                DatabaseManager._instance._initialized = False  # Force re-read env

            db_manager = DatabaseManager()
            # Mock the driver creation which happens in get_driver or explicit assignment
            db_manager._driver = mock_driver

            # verify_connection in code calls self._driver.session()...
            # Logic: with self._driver.session() as session: session.run("RETURN 1").consume()

            session_mock = MagicMock()
            mock_driver.session.return_value.__enter__.return_value = session_mock

            assert db_manager.is_connected() is True

    def test_verify_connection_failure(self, mock_driver):
        """Test verify_connectivity returns False on exception."""
        with patch.dict(
            os.environ,
            {
                "NEO4J_URI": "bolt://localhost:7687",
                "NEO4J_USERNAME": "u",
                "NEO4J_PASSWORD": "p",
            },
        ):
            db_manager = DatabaseManager()
            db_manager._driver = mock_driver

            mock_driver.session.side_effect = Exception("Connection refused")

            assert db_manager.is_connected() is False

    def test_initialization_with_database(self, mock_driver):
        """Test that DatabaseManager reads NEO4J_DATABASE from env."""
        with patch.dict(
            os.environ,
            {
                "NEO4J_URI": "bolt://localhost:7687",
                "NEO4J_USERNAME": "neo4j",
                "NEO4J_PASSWORD": "password",
                "NEO4J_DATABASE": "mydb",
            },
        ):
            if DatabaseManager._instance:
                DatabaseManager._instance = None
            db_manager = DatabaseManager()
            assert db_manager.neo4j_database == "mydb"

    def test_initialization_without_database(self, mock_driver):
        """Test that neo4j_database is None when NEO4J_DATABASE is not set."""
        env = {
            "NEO4J_URI": "bolt://localhost:7687",
            "NEO4J_USERNAME": "neo4j",
            "NEO4J_PASSWORD": "password",
        }
        with patch.dict(os.environ, env, clear=True):
            if DatabaseManager._instance:
                DatabaseManager._instance = None
            db_manager = DatabaseManager()
            assert db_manager.neo4j_database is None

    def test_get_driver_returns_wrapper_with_database(self, mock_driver):
        """Test get_driver() returns a Neo4jDriverWrapper with the configured database."""
        with patch.dict(
            os.environ,
            {
                "NEO4J_URI": "bolt://localhost:7687",
                "NEO4J_USERNAME": "neo4j",
                "NEO4J_PASSWORD": "password",
                "NEO4J_DATABASE": "mydb",
            },
        ):
            if DatabaseManager._instance:
                DatabaseManager._instance = None
            db_manager = DatabaseManager()
            db_manager._driver = mock_driver

            # Mock the connection test inside get_driver
            session_mock = MagicMock()
            mock_driver.session.return_value.__enter__.return_value = session_mock

            wrapper = db_manager.get_driver()
            assert isinstance(wrapper, Neo4jDriverWrapper)
            assert wrapper._database == "mydb"

    def test_get_driver_returns_wrapper_without_database(self, mock_driver):
        """Test get_driver() returns a Neo4jDriverWrapper with None database when not configured."""
        env = {
            "NEO4J_URI": "bolt://localhost:7687",
            "NEO4J_USERNAME": "neo4j",
            "NEO4J_PASSWORD": "password",
        }
        with patch.dict(os.environ, env, clear=True):
            if DatabaseManager._instance:
                DatabaseManager._instance = None
            db_manager = DatabaseManager()
            db_manager._driver = mock_driver

            session_mock = MagicMock()
            mock_driver.session.return_value.__enter__.return_value = session_mock

            wrapper = db_manager.get_driver()
            assert isinstance(wrapper, Neo4jDriverWrapper)
            assert wrapper._database is None

    def test_is_connected_passes_database_to_session(self, mock_driver):
        """Test is_connected() includes database in session kwargs when neo4j_database is set."""
        with patch.dict(
            os.environ,
            {
                "NEO4J_URI": "bolt://localhost:7687",
                "NEO4J_USERNAME": "u",
                "NEO4J_PASSWORD": "p",
                "NEO4J_DATABASE": "mydb",
            },
        ):
            if DatabaseManager._instance:
                DatabaseManager._instance = None
            db_manager = DatabaseManager()
            db_manager._driver = mock_driver

            session_mock = MagicMock()
            mock_driver.session.return_value.__enter__.return_value = session_mock

            db_manager.is_connected()
            mock_driver.session.assert_called_with(database="mydb")

    def test_is_connected_no_database_in_session(self, mock_driver):
        """Test is_connected() does NOT include database in session kwargs when neo4j_database is None."""
        env = {
            "NEO4J_URI": "bolt://localhost:7687",
            "NEO4J_USERNAME": "u",
            "NEO4J_PASSWORD": "p",
        }
        with patch.dict(os.environ, env, clear=True):
            if DatabaseManager._instance:
                DatabaseManager._instance = None
            db_manager = DatabaseManager()
            db_manager._driver = mock_driver

            session_mock = MagicMock()
            mock_driver.session.return_value.__enter__.return_value = session_mock

            db_manager.is_connected()
            mock_driver.session.assert_called_with()


class TestNeo4jDriverWrapper:
    """Unit tests for the Neo4jDriverWrapper class."""

    def test_session_injects_database_when_set(self):
        """Test session() adds database kwarg when wrapper has a database configured."""
        mock_driver = MagicMock()
        wrapper = Neo4jDriverWrapper(mock_driver, database="mydb")

        wrapper.session()
        mock_driver.session.assert_called_once_with(database="mydb")

    def test_session_no_database_when_none(self):
        """Test session() does NOT add database kwarg when database is None."""
        mock_driver = MagicMock()
        wrapper = Neo4jDriverWrapper(mock_driver, database=None)

        wrapper.session()
        mock_driver.session.assert_called_once_with()

    def test_session_does_not_override_existing_database(self):
        """Test session() respects caller-provided database kwarg."""
        mock_driver = MagicMock()
        wrapper = Neo4jDriverWrapper(mock_driver, database="mydb")

        wrapper.session(database="otherdb")
        mock_driver.session.assert_called_once_with(database="otherdb")

    def test_close_delegates_to_driver(self):
        """Test close() calls close() on the underlying driver."""
        mock_driver = MagicMock()
        wrapper = Neo4jDriverWrapper(mock_driver, database="mydb")

        wrapper.close()
        mock_driver.close.assert_called_once()


class TestTestConnection:
    """Unit tests for DatabaseManager.test_connection() with database parameter."""

    @patch("neo4j.GraphDatabase")
    @patch("socket.socket")
    def test_test_connection_with_database(self, mock_socket_cls, mock_gdb):
        """Test test_connection() passes database to session when provided."""
        # Mock socket connectivity check
        mock_sock = MagicMock()
        mock_socket_cls.return_value = mock_sock
        mock_sock.connect_ex.return_value = 0

        # Mock driver and session
        mock_driver = MagicMock()
        mock_gdb.driver.return_value = mock_driver
        mock_session = MagicMock()
        mock_driver.session.return_value.__enter__ = MagicMock(
            return_value=mock_session
        )
        mock_driver.session.return_value.__exit__ = MagicMock(return_value=False)

        is_connected, error = DatabaseManager.test_connection(
            "bolt://localhost:7687", "neo4j", "password", database="mydb"
        )

        assert is_connected is True
        assert error is None
        mock_driver.session.assert_called_once_with(database="mydb")

    @patch("neo4j.GraphDatabase")
    @patch("socket.socket")
    def test_test_connection_without_database(self, mock_socket_cls, mock_gdb):
        """Test test_connection() does NOT pass database to session when None."""
        mock_sock = MagicMock()
        mock_socket_cls.return_value = mock_sock
        mock_sock.connect_ex.return_value = 0

        mock_driver = MagicMock()
        mock_gdb.driver.return_value = mock_driver
        mock_session = MagicMock()
        mock_driver.session.return_value.__enter__ = MagicMock(
            return_value=mock_session
        )
        mock_driver.session.return_value.__exit__ = MagicMock(return_value=False)

        is_connected, error = DatabaseManager.test_connection(
            "bolt://localhost:7687", "neo4j", "password"
        )

        assert is_connected is True
        assert error is None
        mock_driver.session.assert_called_once_with()


class TestBackendCompatibilityWrappers:
    """Characterization tests for non-Neo4j backend compatibility wrappers."""

    def test_kuzu_session_translates_merge_uid_and_drops_unused_parameters(self):
        """Test Kuzu query translation preserves UID injection and param filtering."""
        from platform_context_graph.core.database_kuzu import KuzuSessionWrapper

        session = KuzuSessionWrapper(MagicMock())
        query, parameters = session._translate_query(
            "MERGE (f:Function {name: $name, path: $path, line_number: $line_number}) RETURN f",
            {
                "name": "do_work",
                "path": "src/tasks.py",
                "line_number": 17,
                "unused": "drop-me",
            },
        )

        assert "uid: $__uid_f" in query
        assert parameters == {
            "name": "do_work",
            "path": "src/tasks.py",
            "line_number": 17,
            "__uid_f": "do_worksrc/tasks.py17",
        }

    def test_kuzu_session_expands_property_updates_for_allowed_fields_only(self):
        """Test Kuzu SET += translation keeps only supported scalar/list fields."""
        from platform_context_graph.core.database_kuzu import KuzuSessionWrapper

        session = KuzuSessionWrapper(MagicMock())
        query, parameters = session._translate_query(
            "MATCH (f:Function {uid: $uid}) SET f += $props RETURN f",
            {
                "uid": "function:1",
                "props": {
                    "name": "do_work",
                    "args": ["tenant_id"],
                    "ignored": "nope",
                    "metadata": {"nested": True},
                },
            },
        )

        assert "SET f.name = $props_name, f.args = $props_args" in query
        assert "ignored" not in query
        assert "metadata" not in query
        assert parameters == {
            "uid": "function:1",
            "props_name": "do_work",
            "props_args": ["tenant_id"],
        }

    def test_falkordb_session_downgrades_unique_constraint_to_index(self):
        """Test FalkorDB schema translation preserves constraint downgrade behavior."""
        from platform_context_graph.core.database_falkordb import FalkorDBSessionWrapper

        session = FalkorDBSessionWrapper(MagicMock())
        translated = session._translate_schema_query(
            "CREATE CONSTRAINT unique_uid IF NOT EXISTS FOR (n:Function) REQUIRE n.uid IS UNIQUE"
        )

        assert translated == "CREATE INDEX FOR (n:Function) ON (n.uid)"

    def test_falkordb_result_wrapper_decodes_byte_header_names(self):
        """Test FalkorDB results keep decoded column names after wrapping."""
        from platform_context_graph.core.database_falkordb import FalkorDBResultWrapper

        result = MagicMock()
        result.header = [["SCALAR", b"name"]]
        result.result_set = [["payments-api"]]

        wrapped = FalkorDBResultWrapper(result)

        assert wrapped.data() == [{"name": "payments-api"}]

    def test_falkordb_session_accepts_positional_parameter_mapping(self):
        """Test FalkorDB sessions accept Neo4j-style positional parameter maps."""
        from platform_context_graph.core.database_falkordb import FalkorDBSessionWrapper

        graph = MagicMock()
        session = FalkorDBSessionWrapper(graph)

        session.run("RETURN $name AS name", {"name": "payments-api"})

        graph.query.assert_called_once_with(
            "RETURN $name AS name", {"name": "payments-api"}
        )

    def test_kuzu_session_accepts_positional_parameter_mapping(self):
        """Test Kuzu sessions accept Neo4j-style positional parameter maps."""
        from platform_context_graph.core.database_kuzu import KuzuSessionWrapper

        conn = MagicMock()
        conn.execute.return_value = None
        session = KuzuSessionWrapper(conn)

        session.run("RETURN $name AS name", {"name": "payments-api"})

        conn.execute.assert_called_once()
        _, parameters = conn.execute.call_args.args
        assert parameters["name"] == "payments-api"
