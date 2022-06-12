import logging
from subprocess import CompletedProcess

import pytest
import requests_mock

from mirror_tool.conf import GitlabMerge, GitlabMergeComments
from mirror_tool.gitlab import GitlabException, GitlabUpdateSession


def test_create_ok(monkeypatch, requests_mocker: requests_mock.Mocker, caplog):
    """GitlabSession can create a merge request."""

    monkeypatch.setenv("GITLAB_MIRROR_TOKEN", "abc123-not-a-real-token")

    merge = GitlabMerge(
        api_v4_url="https://example.com/api",
        project_id=123,
        push_url="https://example.com/push",
        src="some-src",
        dest="some-dest",
    )

    procs = []

    def run_cmd_ok(*args, **kwargs):
        return procs.pop(0)

    # No existing MR.
    requests_mocker.get(
        "https://example.com/api/projects/123/merge_requests?state=opened&source_branch=some-src&target_branch=some-dest",
        json=[],
    )

    requests_mocker.post(
        "https://example.com/api/projects/123/merge_requests",
        status_code=200,
        json={"web_url": "https://example.com/new-mr"},
    )

    caplog.set_level(logging.INFO)
    session = GitlabUpdateSession(merge, run_cmd=run_cmd_ok, updates=[])

    # Set up the commands we expect it to run...
    # git fetch
    procs.append(CompletedProcess([], returncode=0))

    # merge-base is-ancestor (1 means is not ancestor)
    procs.append(CompletedProcess([], returncode=1))

    # push
    procs.append(CompletedProcess([], returncode=0))

    # It should succeed
    session.ensure_merge_request_exists()

    # It should tell us what was done
    assert "Created: https://example.com/new-mr" in caplog.text

    # This is what it should have created
    assert requests_mocker.request_history[-1].json() == {
        "allow_collaboration": True,
        "description": "Automated update of dependencies.",
        "labels": ["mirror-tool"],
        "source_branch": "some-src",
        "squash": False,
        "target_branch": "some-dest",
        "title": "Update mirror",
    }


def test_update_ok(monkeypatch, requests_mocker: requests_mock.Mocker, caplog):
    """GitlabSession can update a merge request."""

    monkeypatch.setenv("GITLAB_MIRROR_TOKEN", "abc123-not-a-real-token")
    monkeypatch.setenv("SOMEVAR", "someval")

    merge = GitlabMerge(
        api_v4_url="https://example.com/api",
        project_id=123,
        push_url="https://example.com/push",
        src="some-src",
        dest="some-dest",
        comment=GitlabMergeComments(
            update="mr updated {{env.SOMEVAR}}",
        ),
    )

    procs = []

    def run_cmd_ok(*args, **kwargs):
        print(args)
        return procs.pop(0)

    # Initial request fails with conflict.
    requests_mocker.post(
        "https://example.com/api/projects/123/merge_requests",
        status_code=409,
        json={},
    )

    # Then it should try to find the existing MR.
    requests_mocker.get(
        "https://example.com/api/projects/123/merge_requests?state=opened&source_branch=some-src&target_branch=some-dest",
        status_code=200,
        json=[
            {
                "web_url": "https://example.com/existing-mr",
                "labels": ["mirror-tool"],
                "iid": 112233,
                "sha": "aa112233",
            }
        ],
    )

    # And update that one...
    requests_mocker.put(
        "https://example.com/api/projects/123/merge_requests/112233",
        status_code=201,
        json={},
    )

    # Then post a comment
    requests_mocker.post(
        "https://example.com/api/projects/123/merge_requests/112233/notes",
        status_code=200,
        json={},
    )

    caplog.set_level(logging.INFO)
    session = GitlabUpdateSession(merge, run_cmd=run_cmd_ok, updates=[])

    # Set up the commands we expect it to run...
    # git fetch
    procs.append(CompletedProcess([], returncode=0))

    # merge-base is-ancestor (1 == 'is not ancestor')
    procs.append(CompletedProcess([], returncode=1))

    # git fetch
    procs.append(CompletedProcess([], returncode=0))

    # git diff (1 == 'there are changes')
    procs.append(CompletedProcess([], returncode=1))

    # push
    procs.append(CompletedProcess([], returncode=0))

    # It should succeed
    session.ensure_merge_request_exists()

    # It should tell us what was done
    assert "Commented on: https://example.com/existing-mr" in caplog.text
    assert "Updated: https://example.com/existing-mr" in caplog.text

    # Check the requests
    update_req = requests_mocker.request_history[-2]
    comment_req = requests_mocker.request_history[-1]

    assert update_req.json() == {
        "allow_collaboration": True,
        "description": "Automated update of dependencies.",
        "labels": ["mirror-tool"],
        "squash": False,
        "title": "Update mirror",
    }

    assert comment_req.json() == {"body": "mr updated someval"}


def test_update_skips_no_diff(
    monkeypatch, requests_mocker: requests_mock.Mocker, caplog
):
    """GitlabSession can skip updating a merge request when there are no changes."""

    monkeypatch.setenv("GITLAB_MIRROR_TOKEN", "abc123-not-a-real-token")
    monkeypatch.setenv("SOMEVAR", "someval")

    merge = GitlabMerge(
        api_v4_url="https://example.com/api",
        project_id=123,
        push_url="https://example.com/push",
        src="some-src",
        dest="some-dest",
        comment=GitlabMergeComments(
            update="mr updated {{env.SOMEVAR}}",
        ),
    )

    procs = []

    def run_cmd_ok(*args, **kwargs):
        print(args)
        return procs.pop(0)

    # It should try to find the existing MR.
    requests_mocker.get(
        "https://example.com/api/projects/123/merge_requests?state=opened&source_branch=some-src&target_branch=some-dest",
        status_code=200,
        json=[
            {
                "web_url": "https://example.com/existing-mr",
                "labels": ["mirror-tool"],
                "iid": 112233,
                "sha": "aa112233",
            }
        ],
    )

    caplog.set_level(logging.INFO)
    session = GitlabUpdateSession(merge, run_cmd=run_cmd_ok, updates=[])

    # Set up the commands we expect it to run...
    # git fetch
    procs.append(CompletedProcess([], returncode=0))

    # merge-base is-ancestor (1 == 'is not ancestor')
    procs.append(CompletedProcess([], returncode=1))

    # git fetch
    procs.append(CompletedProcess([], returncode=0))

    # git diff (0 == 'there are no changes')
    procs.append(CompletedProcess([], returncode=0))

    # It should succeed
    session.ensure_merge_request_exists()

    # It should tell us no update was needed
    assert "https://example.com/existing-mr does not need an update" in caplog.text


def test_update_rejects_unknown(monkeypatch, requests_mocker: requests_mock.Mocker):
    """GitlabSession refuses to update an MR if not labelled as created by mirror-tool."""

    monkeypatch.setenv("GITLAB_MIRROR_TOKEN", "abc123-not-a-real-token")

    merge = GitlabMerge(
        api_v4_url="https://example.com/api",
        project_id=123,
        push_url="https://example.com/push",
        src="some-src",
        dest="some-dest",
    )

    def run_cmd_ok(*args, **kwargs):
        pass

    # Initial request fails with conflict.
    requests_mocker.post(
        "https://example.com/api/projects/123/merge_requests",
        status_code=409,
        json={},
    )

    # Then it should try to find the existing MR.
    requests_mocker.get(
        "https://example.com/api/projects/123/merge_requests?state=opened&source_branch=some-src&target_branch=some-dest",
        status_code=200,
        json=[
            {
                "web_url": "https://example.com/existing-mr",
                "labels": ["whatever"],
                "iid": 112233,
            }
        ],
    )

    session = GitlabUpdateSession(merge, run_cmd=run_cmd_ok, updates=[])

    # Make this check return False without having to mock the commands
    monkeypatch.setattr(session, "revision_in_remote_branch", lambda *_: False)

    # It should fail
    with pytest.raises(GitlabException) as excinfo:
        session.ensure_merge_request_exists()

    # It should tell us why
    assert (
        "An existing merge request https://example.com/existing-mr was found, "
        "but it was apparently not created by mirror-tool! Refusing to update."
    ) in str(excinfo.value)


def test_update_not_found(monkeypatch, requests_mocker: requests_mock.Mocker):
    """GitlabSession fails to update MR if existing MR can't be found."""

    monkeypatch.setenv("GITLAB_MIRROR_TOKEN", "abc123-not-a-real-token")

    merge = GitlabMerge(
        api_v4_url="https://example.com/api",
        project_id=123,
        push_url="https://example.com/push",
        src="some-src",
        dest="some-dest",
    )

    def run_cmd_ok(*args, **kwargs):
        pass

    # Initial request fails with conflict.
    requests_mocker.post(
        "https://example.com/api/projects/123/merge_requests",
        status_code=409,
        json={},
    )

    # Then it should try to find the existing MR.
    requests_mocker.get(
        "https://example.com/api/projects/123/merge_requests?state=opened&source_branch=some-src&target_branch=some-dest",
        status_code=200,
        # unexpected: found no MR
        json=[],
    )

    session = GitlabUpdateSession(merge, run_cmd=run_cmd_ok, updates=[])

    # Make this check return False without having to mock the commands
    monkeypatch.setattr(session, "revision_in_remote_branch", lambda *_: False)

    # It should fail
    with pytest.raises(GitlabException) as excinfo:
        session.ensure_merge_request_exists()

    # It should tell us why
    assert (
        "Failed to create MR due to conflict, "
        "but also failed to locate an existing MR!"
    ) in str(excinfo.value)


def test_update_noop_if_present(monkeypatch, requests_mocker: requests_mock.Mocker):
    """Session does nothing if desired revision is already present in dest."""

    monkeypatch.setenv("GITLAB_MIRROR_TOKEN", "abc123-not-a-real-token")

    merge = GitlabMerge(
        api_v4_url="https://example.com/api",
        project_id=123,
        push_url="https://example.com/push",
        src="some-src",
        dest="some-dest",
    )

    def run_cmd_error(*args, **kwargs):
        # it's not expected to run any commands
        raise RuntimeError("Should not get here!")

    session = GitlabUpdateSession(merge, run_cmd=run_cmd_error, updates=[])

    # Make this check return True without having to mock the commands
    monkeypatch.setattr(session, "revision_in_remote_branch", lambda *_: True)

    # It should succeed
    session.ensure_merge_request_exists()

    # Lack of any requests_mocker or run_cmd mocking proves we didn't actually
    # do any commands or requests.
