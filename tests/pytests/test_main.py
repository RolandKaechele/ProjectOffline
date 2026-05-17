"""Tests for main.py - Application entry point.

These tests verify the basic structure of main.py without full integration testing,
which is difficult due to PyQt5's QApplication singleton and complex initialization.
"""

import pytest
from unittest.mock import MagicMock, patch, call
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'src')))


# ---------------------------------------------------------------------------
# Module Structure Tests
# ---------------------------------------------------------------------------

class TestMainModule:
    def test_main_function_exists(self):
        """Verify that main() function exists."""
        import main
        assert hasattr(main, 'main')
        assert callable(main.main)

    def test_main_module_has_docstring(self):
        """Verify that main.py has documentation."""
        import main
        assert main.__doc__ is not None
        assert len(main.__doc__) > 0


# ---------------------------------------------------------------------------
# Argument Parsing Tests (without executing main)
# ---------------------------------------------------------------------------

class TestArgumentParsing:
    def test_argparse_with_no_args(self):
        """Test that argparse handles no arguments."""
        import argparse
        parser = argparse.ArgumentParser(description="Project Offline")
        parser.add_argument('--open', type=str, help='Path to a Microsoft Project file to open at startup')
        parser.add_argument('--debug', '-v', action='store_true', help='Enable verbose debug output')
        
        args = parser.parse_args([])
        assert args.open is None
        assert args.debug is False

    def test_argparse_with_open_arg(self):
        """Test that argparse handles --open argument."""
        import argparse
        parser = argparse.ArgumentParser(description="Project Offline")
        parser.add_argument('--open', type=str, help='Path to a Microsoft Project file to open at startup')
        parser.add_argument('--debug', '-v', action='store_true', help='Enable verbose debug output')
        
        args = parser.parse_args(['--open', 'test.mpp'])
        assert args.open == 'test.mpp'
        assert args.debug is False

    def test_argparse_with_debug_flag(self):
        """Test that argparse handles --debug flag."""
        import argparse
        parser = argparse.ArgumentParser(description="Project Offline")
        parser.add_argument('--open', type=str, help='Path to a Microsoft Project file to open at startup')
        parser.add_argument('--debug', '-v', action='store_true', help='Enable verbose debug output')
        
        args = parser.parse_args(['--debug'])
        assert args.open is None
        assert args.debug is True

    def test_argparse_with_verbose_short_flag(self):
        """Test that argparse handles -v flag."""
        import argparse
        parser = argparse.ArgumentParser(description="Project Offline")
        parser.add_argument('--open', type=str, help='Path to a Microsoft Project file to open at startup')
        parser.add_argument('--debug', '-v', action='store_true', help='Enable verbose debug output')
        
        args = parser.parse_args(['-v'])
        assert args.open is None
        assert args.debug is True

    def test_argparse_with_all_args(self):
        """Test that argparse handles both --open and --debug."""
        import argparse
        parser = argparse.ArgumentParser(description="Project Offline")
        parser.add_argument('--open', type=str, help='Path to a Microsoft Project file to open at startup')
        parser.add_argument('--debug', '-v', action='store_true', help='Enable verbose debug output')
        
        args = parser.parse_args(['--open', 'project.mpp', '--debug'])
        assert args.open == 'project.mpp'
        assert args.debug is True


# ---------------------------------------------------------------------------
# Integration Test (mocked execution path)
# ---------------------------------------------------------------------------

class TestMainExecution:
    def test_main_calls_expected_components(self, qapp):
        """Test that main() creates expected components when fully mocked."""
        test_args = ['main.py']
        
        # Mock all heavy dependencies before importing main
        with patch('sys.argv', test_args), \
             patch('main.QApplication') as mock_qapp_class, \
             patch('main.ProjectLogic') as mock_logic_class, \
             patch('main.ProjectFileHandler') as mock_handler_class, \
             patch('main.MainWindow') as mock_window_class, \
             patch('sys.exit'):
            
            # Setup mock return values
            mock_app = MagicMock()
            mock_app.exec_.return_value = 0
            mock_qapp_class.return_value = mock_app
            
            mock_logic = MagicMock()
            mock_logic_class.return_value = mock_logic
            
            mock_handler = MagicMock()
            mock_handler_class.return_value = mock_handler
            
            mock_window = MagicMock()
            mock_window_class.return_value = mock_window
            
            # Import and run main
            import main as main_module
            try:
                main_module.main()
            except SystemExit:
                pass  # main() calls sys.exit, which we're mocking
            
            # Verify component creation
            mock_logic_class.assert_called_once()
            mock_handler_class.assert_called_once_with(mock_logic)
            mock_window_class.assert_called_once_with(mock_logic, mock_handler)
            mock_window.show.assert_called_once()

    def test_main_opens_file_when_open_arg_provided(self, qapp):
        """Test that main() opens file when --open is provided."""
        test_args = ['main.py', '--open', 'test.mpp']
        
        with patch('sys.argv', test_args), \
             patch('main.QApplication') as mock_qapp_class, \
             patch('main.ProjectLogic') as mock_logic_class, \
             patch('main.ProjectFileHandler') as mock_handler_class, \
             patch('main.MainWindow') as mock_window_class, \
             patch('sys.exit'):
            
            mock_app = MagicMock()
            mock_app.exec_.return_value = 0
            mock_qapp_class.return_value = mock_app
            
            mock_logic = MagicMock()
            mock_logic_class.return_value = mock_logic
            
            mock_handler = MagicMock()
            mock_handler_class.return_value = mock_handler
            
            mock_window = MagicMock()
            mock_window_class.return_value = mock_window
            
            import main as main_module
            try:
                main_module.main()
            except SystemExit:
                pass
            
            # Verify file was opened
            mock_window.open_project_file.assert_called_once_with('test.mpp')

    def test_main_enables_debug_when_debug_flag_provided(self, qapp):
        """Test that main() enables debug mode when --debug is provided."""
        test_args = ['main.py', '--debug']
        
        with patch('sys.argv', test_args), \
             patch('main.QApplication') as mock_qapp_class, \
             patch('main.ProjectLogic') as mock_logic_class, \
             patch('main.ProjectFileHandler') as mock_handler_class, \
             patch('main.MainWindow') as mock_window_class, \
             patch('sys.exit'):
            
            # Need to patch set_debug before main imports it
            with patch('app_debug.set_debug') as mock_set_debug:
                mock_app = MagicMock()
                mock_app.exec_.return_value = 0
                mock_qapp_class.return_value = mock_app
                
                mock_logic = MagicMock()
                mock_logic_class.return_value = mock_logic
                
                mock_handler = MagicMock()
                mock_handler_class.return_value = mock_handler
                
                mock_window = MagicMock()
                mock_window_class.return_value = mock_window
                
                import main as main_module
                try:
                    main_module.main()
                except SystemExit:
                    pass
                
                # Verify debug was enabled
                mock_set_debug.assert_called_once_with(True)


# ---------------------------------------------------------------------------
# Tool Discovery Tests (bundled-first priority)
# ---------------------------------------------------------------------------

class TestFindAndConfigureJdk:
    def test_bundled_jdk_preferred_over_system(self, tmp_path):
        """Bundled JDK at <exe_dir>/jdk sets JAVA_HOME, even if JAVA_HOME was already set."""
        import main as main_module

        exe_dir = tmp_path / "exe"
        jdk_bin = exe_dir / "jdk" / "bin"
        jdk_bin.mkdir(parents=True)
        (jdk_bin / "java.exe").touch()

        fake_src = tmp_path / "src" / "main.py"
        fake_src.parent.mkdir(parents=True)

        with patch("sys.executable", str(exe_dir / "python.exe")), \
             patch.object(main_module, "__file__", str(fake_src)), \
             patch.dict(os.environ, {"JAVA_HOME": "/system/java", "PATH": "/old"}, clear=False):
            main_module._find_and_configure_jdk()
            assert os.environ["JAVA_HOME"] == str(exe_dir / "jdk")
            assert str(exe_dir / "jdk" / "bin") in os.environ["PATH"].split(os.pathsep)

    def test_system_java_fallback_when_no_bundled_jdk(self, tmp_path):
        """When no bundled JDK exists, JAVA_HOME is left unchanged (system Java used)."""
        import main as main_module

        exe_dir = tmp_path / "exe"
        exe_dir.mkdir()

        fake_src = tmp_path / "src" / "main.py"
        fake_src.parent.mkdir(parents=True)

        with patch("sys.executable", str(exe_dir / "python.exe")), \
             patch.object(main_module, "__file__", str(fake_src)), \
             patch.dict(os.environ, {"JAVA_HOME": "/system/java"}, clear=False):
            main_module._find_and_configure_jdk()
            assert os.environ.get("JAVA_HOME") == "/system/java"


class TestFindAndConfigureGit:
    def test_bundled_git_preferred_over_system(self, tmp_path):
        """Bundled git.exe at <exe_dir>/git/cmd is prepended to PATH; shutil.which not consulted."""
        import main as main_module

        exe_dir = tmp_path / "exe"
        git_cmd_dir = exe_dir / "git" / "cmd"
        git_cmd_dir.mkdir(parents=True)
        (git_cmd_dir / "git.exe").touch()

        fake_src = tmp_path / "src" / "main.py"
        fake_src.parent.mkdir(parents=True)

        with patch("sys.executable", str(exe_dir / "python.exe")), \
             patch.object(main_module, "__file__", str(fake_src)), \
             patch.dict(os.environ, {"PATH": "/old"}, clear=False), \
             patch("shutil.which") as mock_which:
            main_module._find_and_configure_git()
            assert str(git_cmd_dir) in os.environ["PATH"].split(os.pathsep)
            mock_which.assert_not_called()

    def test_system_git_fallback_when_no_bundled_git(self, tmp_path):
        """When no bundled git exists, shutil.which is consulted as fallback."""
        import main as main_module

        exe_dir = tmp_path / "exe"
        exe_dir.mkdir()

        fake_src = tmp_path / "src" / "main.py"
        fake_src.parent.mkdir(parents=True)

        with patch("sys.executable", str(exe_dir / "python.exe")), \
             patch.object(main_module, "__file__", str(fake_src)), \
             patch.dict(os.environ, {"PATH": "/old"}, clear=False), \
             patch("shutil.which", return_value="/usr/bin/git.exe") as mock_which:
            main_module._find_and_configure_git()
            mock_which.assert_called_once_with("git.exe")


class TestFindAndConfigureSvn:
    def test_bundled_svn_preferred_over_system(self, tmp_path):
        """Bundled svn.exe at <exe_dir>/svn is prepended to PATH; shutil.which not consulted."""
        import main as main_module

        exe_dir = tmp_path / "exe"
        svn_dir = exe_dir / "svn"
        svn_dir.mkdir(parents=True)
        (svn_dir / "svn.exe").touch()

        fake_src = tmp_path / "src" / "main.py"
        fake_src.parent.mkdir(parents=True)

        with patch("sys.executable", str(exe_dir / "python.exe")), \
             patch.object(main_module, "__file__", str(fake_src)), \
             patch.dict(os.environ, {"PATH": "/old"}, clear=False), \
             patch("shutil.which") as mock_which:
            main_module._find_and_configure_svn()
            assert str(svn_dir) in os.environ["PATH"].split(os.pathsep)
            mock_which.assert_not_called()

    def test_system_svn_fallback_when_no_bundled_svn(self, tmp_path):
        """When no bundled svn exists, shutil.which is consulted as fallback."""
        import main as main_module

        exe_dir = tmp_path / "exe"
        exe_dir.mkdir()

        fake_src = tmp_path / "src" / "main.py"
        fake_src.parent.mkdir(parents=True)

        with patch("sys.executable", str(exe_dir / "python.exe")), \
             patch.object(main_module, "__file__", str(fake_src)), \
             patch.dict(os.environ, {"PATH": "/old"}, clear=False), \
             patch("shutil.which", return_value="/usr/bin/svn.exe") as mock_which:
            main_module._find_and_configure_svn()
            mock_which.assert_called_once_with("svn.exe")
