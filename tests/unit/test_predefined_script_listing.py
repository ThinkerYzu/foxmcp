"""
Tests for the script listing in content_execute_predefined's description

A client can only call a predefined script it knows the name of, and the tool's
description is the one place every client reads without being asked. These
tests cover what goes into that listing and what is left out of it.
"""

import stat

import pytest

import test_imports  # Automatic path setup
from server.mcp_tools import (
    MAX_SCRIPT_DESCRIPTION_LENGTH,
    SCRIPT_HEADER_LINES,
    FoxMCPTools,
    describe_predefined_scripts,
    read_script_header,
)


def write_script(directory, name, body, executable=True):
    """Create a script and return its path"""
    path = directory / name
    path.write_text(body)
    if executable:
        path.chmod(path.stat().st_mode | stat.S_IXUSR)
    return path


class TestMarkers:

    def test_description_and_args_markers(self, tmp_path):
        path = write_script(tmp_path, 'a.sh',
                            '#!/bin/bash\n# foxmcp-description: Does a thing\n# foxmcp-args: <name> [count]\n')
        assert read_script_header(path) == ('Does a thing', '<name> [count]')

    @pytest.mark.parametrize('prefix', ['#', '//', '--', ''])
    def test_marker_found_whatever_the_comment_syntax(self, tmp_path, prefix):
        path = write_script(tmp_path, 'a', f'{prefix} foxmcp-description: Does a thing\n')
        assert read_script_header(path)[0] == 'Does a thing'

    def test_args_marker_is_optional(self, tmp_path):
        path = write_script(tmp_path, 'a.sh', '#!/bin/bash\n# foxmcp-description: Takes nothing\n')
        assert read_script_header(path) == ('Takes nothing', None)

    def test_marker_past_the_header_is_ignored(self, tmp_path):
        """Only the header is read, so a marker deep in the file does not count"""
        body = '#!/bin/bash\necho hi\n' * SCRIPT_HEADER_LINES + '# foxmcp-description: Too late\n'
        path = write_script(tmp_path, 'a.sh', body)
        assert read_script_header(path) == (None, None)

    def test_long_description_and_args_are_cut(self, tmp_path):
        long_text = 'x' * (MAX_SCRIPT_DESCRIPTION_LENGTH + 100)
        path = write_script(tmp_path, 'a.sh',
                            f'# foxmcp-description: {long_text}\n# foxmcp-args: {long_text}\n')
        description, args = read_script_header(path)

        assert description == 'x' * MAX_SCRIPT_DESCRIPTION_LENGTH + '...'
        assert args == 'x' * MAX_SCRIPT_DESCRIPTION_LENGTH + '...'


class TestFirstCommentFallback:

    def test_first_comment_stands_in_for_a_missing_marker(self, tmp_path):
        path = write_script(tmp_path, 'a.sh', '#!/bin/bash\n\n# Plays the video\n# More detail\n')
        assert read_script_header(path) == ('Plays the video', None)

    def test_marker_wins_over_the_first_comment(self, tmp_path):
        path = write_script(tmp_path, 'a.sh',
                            '#!/bin/bash\n# Old title\n# foxmcp-description: The real description\n')
        assert read_script_header(path)[0] == 'The real description'

    @pytest.mark.parametrize('boilerplate', [
        '#',
        '# -*- coding: utf-8 -*-',
        '# vim: set ts=4:',
        '# Copyright (c) 2024 Someone',
        '# SPDX-License-Identifier: MIT',
        '# Usage: a.sh <name>',
        '# Example: a.sh foo',
        '# Arguments:',
    ])
    def test_boilerplate_lines_are_skipped(self, tmp_path, boilerplate):
        path = write_script(tmp_path, 'a.sh', f'#!/bin/bash\n{boilerplate}\n# Does the thing\n')
        assert read_script_header(path)[0] == 'Does the thing'

    def test_comment_after_code_is_never_taken(self, tmp_path):
        """A comment inside the code describes that code, not the script"""
        path = write_script(tmp_path, 'a.sh', '#!/bin/bash\nset -e\n# loop over the tabs\n')
        assert read_script_header(path) == (None, None)

    def test_python_comment_prefix(self, tmp_path):
        path = write_script(tmp_path, 'a.py', '#!/usr/bin/env python3\n# Prints the page title\nimport sys\n')
        assert read_script_header(path)[0] == 'Prints the page title'


class TestListing:

    def test_scripts_listed_in_name_order_with_args(self, tmp_path):
        write_script(tmp_path, 'zeta.sh', '# foxmcp-description: Last one\n')
        write_script(tmp_path, 'alpha.sh', '# foxmcp-description: First one\n# foxmcp-args: [x]\n')

        listing = describe_predefined_scripts(str(tmp_path))

        assert listing.splitlines() == [
            "Available scripts:",
            "- alpha.sh [x]: First one",
            "- zeta.sh: Last one",
        ]

    def test_only_runnable_files_are_listed(self, tmp_path):
        """What the tool would refuse to run must not be offered"""
        write_script(tmp_path, 'runs.sh', '# foxmcp-description: Runs\n')
        write_script(tmp_path, 'inert.sh', '# foxmcp-description: Not executable\n', executable=False)
        write_script(tmp_path, '.hidden.sh', '# foxmcp-description: Dot file\n')
        write_script(tmp_path, 'bad name.sh', '# foxmcp-description: Space in name\n')
        (tmp_path / 'subdir').mkdir()

        listing = describe_predefined_scripts(str(tmp_path))

        assert 'runs.sh' in listing
        for left_out in ('inert.sh', '.hidden.sh', 'bad name.sh', 'subdir'):
            assert left_out not in listing

    def test_undescribed_scripts_share_one_line(self, tmp_path):
        write_script(tmp_path, 'described.sh', '# foxmcp-description: Has one\n')
        write_script(tmp_path, 'bare.sh', '#!/bin/bash\necho hi\n')
        write_script(tmp_path, 'also-bare.sh', '#!/bin/bash\n')

        listing = describe_predefined_scripts(str(tmp_path))

        assert listing.splitlines()[-1] == "Also available, without a description: also-bare.sh, bare.sh"

    def test_only_undescribed_scripts(self, tmp_path):
        write_script(tmp_path, 'bare.sh', '#!/bin/bash\necho hi\n')

        listing = describe_predefined_scripts(str(tmp_path))

        assert listing.splitlines()[-1] == "Without a description: bare.sh"


class TestNothingToList:

    def test_unset_directory(self):
        assert describe_predefined_scripts(None) == "No scripts are available: FOXMCP_EXT_SCRIPTS is not set."

    def test_missing_directory(self, tmp_path, caplog):
        missing = tmp_path / 'absent'

        listing = describe_predefined_scripts(str(missing))

        assert listing == "No scripts are available: the scripts directory cannot be read."
        assert str(missing) in caplog.text

    def test_directory_without_runnable_files(self, tmp_path):
        write_script(tmp_path, 'inert.sh', '#!/bin/bash\n', executable=False)
        assert describe_predefined_scripts(str(tmp_path)) == (
            "No scripts are available: the scripts directory has none that can run."
        )

    def test_listing_does_not_reveal_the_directory(self, tmp_path):
        """The path is the server's business; the log records it, the client does not need it"""
        write_script(tmp_path, 'a.sh', '# foxmcp-description: Does a thing\n')
        assert str(tmp_path) not in describe_predefined_scripts(str(tmp_path))


class TestRegisteredDescription:

    @pytest.mark.asyncio
    async def test_listing_reaches_the_tool_description(self, tmp_path, monkeypatch):
        write_script(tmp_path, 'greet.sh', '# foxmcp-description: Says hello\n# foxmcp-args: <name>\n')
        monkeypatch.setenv('FOXMCP_EXT_SCRIPTS', str(tmp_path))

        tool = await FoxMCPTools(None).mcp.get_tool('content_execute_predefined')

        assert tool.description.startswith('Execute a predefined external script')
        assert '- greet.sh <name>: Says hello' in tool.description

    @pytest.mark.asyncio
    async def test_argument_descriptions_survive(self, tmp_path, monkeypatch):
        """Passing a description must not cost the per-argument ones from the docstring"""
        monkeypatch.setenv('FOXMCP_EXT_SCRIPTS', str(tmp_path))

        tool = await FoxMCPTools(None).mcp.get_tool('content_execute_predefined')

        for argument in ('tab_id', 'script_name', 'script_args'):
            assert tool.parameters['properties'][argument].get('description')

    def test_disabled_group_never_reads_the_directory(self, monkeypatch):
        """A server that does not offer the tool has no reason to list scripts"""
        calls = []
        monkeypatch.setattr('server.mcp_tools.describe_predefined_scripts',
                            lambda scripts_dir: calls.append(scripts_dir) or '')

        FoxMCPTools(None, disabled_groups=['content'])

        assert calls == []
