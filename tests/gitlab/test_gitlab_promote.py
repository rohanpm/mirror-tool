import logging
from subprocess import CompletedProcess

import requests_mock

from mirror_tool.conf import GitlabPromote
from mirror_tool.gitlab import GitlabPromoteSession


def test_promote_noop(monkeypatch, requests_mocker: requests_mock.Mocker, caplog):
    """Session does nothing if no MR eligible for promotion."""

    monkeypatch.setenv("GITLAB_MIRROR_TOKEN", "abc123-not-a-real-token")

    promote = GitlabPromote(
        api_v4_url="https://example.com/api",
        project_id=123,
        push_url="https://example.com/push",
        src="some-src",
        dest="some-dest",
    )

    def run_cmd_ok(*args, **kwargs):
        pass

    # It should try to find an existing MR - make it find nothing.
    requests_mocker.get(
        "https://example.com/api/projects/123/merge_requests?target_branch=some-src&labels=mirror-tool&state=merged",
        status_code=200,
        json=[],
    )

    caplog.set_level(logging.INFO)
    session = GitlabPromoteSession(promote, run_cmd=run_cmd_ok)

    # It should succeed
    session.ensure_promotion_merge_request_exists()

    # But not actually do anything
    assert "No eligible MR for promotion" in caplog.text


def test_promote_already_present(
    monkeypatch, requests_mocker: requests_mock.Mocker, caplog
):
    """Session does nothing if revision for promote is already in target branch."""

    monkeypatch.setenv("GITLAB_MIRROR_TOKEN", "abc123-not-a-real-token")

    promote = GitlabPromote(
        api_v4_url="https://example.com/api",
        project_id=123,
        push_url="https://example.com/push",
        src="some-src",
        dest="some-dest",
    )

    cmd_outputs = []

    def run_cmd_ok(*args, **kwargs):
        return cmd_outputs.pop(0)

    # It should try to find an existing MR - make it find one.
    requests_mocker.get(
        "https://example.com/api/projects/123/merge_requests?target_branch=some-src&labels=mirror-tool&state=merged",
        status_code=200,
        json=[
            {
                "web_url": "https://example.com/some-mr",
                "merge_commit_sha": "a1b2c3",
                "labels": ["mirror-tool"],
            }
        ],
    )

    # fetch: succeeds
    cmd_outputs.append(CompletedProcess([], 0))

    # merge-base is-ancestor: 0 means it is already in dest branch
    cmd_outputs.append(CompletedProcess([], 0))

    caplog.set_level(logging.INFO)
    session = GitlabPromoteSession(promote, run_cmd=run_cmd_ok)

    # It should succeed
    session.ensure_promotion_merge_request_exists()

    # But not actually do anything
    assert (
        "Revision a1b2c3 is already reachable from remote some-dest."
    ) in caplog.text


def test_promote_create_mr(monkeypatch, requests_mocker: requests_mock.Mocker, caplog):
    """Session creates MR as needed for promotion."""

    monkeypatch.setenv("GITLAB_MIRROR_TOKEN", "abc123-not-a-real-token")

    promote = GitlabPromote(
        api_v4_url="https://example.com/api",
        project_id=123,
        push_url="https://example.com/push",
        src="some-src",
        dest="some-dest",
    )

    cmd_outputs = []

    def run_cmd_ok(*args, **kwargs):
        return cmd_outputs.pop(0)

    # It should try to find an existing MR - make it find one.
    requests_mocker.get(
        "https://example.com/api/projects/123/merge_requests?target_branch=some-src&labels=mirror-tool&state=merged",
        status_code=200,
        json=[
            {
                "web_url": "https://example.com/some-mr",
                "merge_commit_sha": "a1b2c3",
                "labels": ["mirror-tool"],
            }
        ],
    )

    # It should try to create an MR as well.
    requests_mocker.post(
        "https://example.com/api/projects/123/merge_requests",
        status_code=200,
        json={"web_url": "https://example.com/new-mr"},
    )

    # fetch: ok
    cmd_outputs.append(CompletedProcess([], 0))

    # merge-base is-ancestor: no it isn't
    cmd_outputs.append(CompletedProcess([], 1))

    # git push: ok
    cmd_outputs.append(CompletedProcess([], 0))

    caplog.set_level(logging.INFO)
    session = GitlabPromoteSession(promote, run_cmd=run_cmd_ok)

    # It should succeed
    session.ensure_promotion_merge_request_exists()

    # It should tell us what it did
    assert "Created: https://example.com/new-mr" in caplog.text

    # This is what it should have created
    assert requests_mocker.request_history[-1].json() == {
        "allow_collaboration": True,
        "description": "Automated promotion between branches.",
        "labels": ["mirror-tool"],
        "source_branch": "mirror-tool/promote-some-src-to-some-dest",
        "squash": False,
        "target_branch": "some-dest",
        "title": "Promote changes",
    }


# def test_update_ok(monkeypatch, requests_mocker: requests_mock.Mocker, caplog):
#     """GitlabSession can update a merge request."""

#     monkeypatch.setenv("GITLAB_MIRROR_TOKEN", "abc123-not-a-real-token")
#     monkeypatch.setenv("SOMEVAR", "someval")

#     merge = GitlabMerge(
#         api_v4_url="https://example.com/api",
#         project_id=123,
#         push_url="https://example.com/push",
#         src="some-src",
#         dest="some-dest",
#         comment=GitlabMergeComments(
#             update="mr updated {{env.SOMEVAR}}",
#         ),
#     )

#     def run_cmd_ok(*args, **kwargs):
#         pass

#     # Initial request fails with conflict.
#     requests_mocker.post(
#         "https://example.com/api/projects/123/merge_requests",
#         status_code=409,
#         json={},
#     )

#     # Then it should try to find the existing MR.
#     requests_mocker.get(
#         "https://example.com/api/projects/123/merge_requests?state=opened&source_branch=some-src&target_branch=some-dest",
#         status_code=200,
#         json=[
#             {
#                 "web_url": "https://example.com/existing-mr",
#                 "labels": ["mirror-tool"],
#                 "iid": 112233,
#             }
#         ],
#     )

#     # And update that one...
#     requests_mocker.put(
#         "https://example.com/api/projects/123/merge_requests/112233",
#         status_code=201,
#         json={},
#     )

#     # Then post a comment
#     requests_mocker.post(
#         "https://example.com/api/projects/123/merge_requests/112233/notes",
#         status_code=200,
#         json={},
#     )

#     caplog.set_level(logging.INFO)
#     session = GitlabUpdateSession(merge, run_cmd=run_cmd_ok, updates=[])

#     # It should succeed
#     session.ensure_merge_request_exists()

#     # It should tell us what was done
#     assert "Commented on: https://example.com/existing-mr" in caplog.text
#     assert "Updated: https://example.com/existing-mr" in caplog.text

#     # Check the requests
#     update_req = requests_mocker.request_history[-2]
#     comment_req = requests_mocker.request_history[-1]

#     assert update_req.json() == {
#         "allow_collaboration": True,
#         "description": "Automated update of dependencies.",
#         "labels": ["mirror-tool"],
#         "squash": False,
#         "title": "Update mirror",
#     }

#     assert comment_req.json() == {"body": "mr updated someval"}


# def test_update_rejects_unknown(monkeypatch, requests_mocker: requests_mock.Mocker):
#     """GitlabSession refuses to update an MR if not labelled as created by mirror-tool."""

#     monkeypatch.setenv("GITLAB_MIRROR_TOKEN", "abc123-not-a-real-token")

#     merge = GitlabMerge(
#         api_v4_url="https://example.com/api",
#         project_id=123,
#         push_url="https://example.com/push",
#         src="some-src",
#         dest="some-dest",
#     )

#     def run_cmd_ok(*args, **kwargs):
#         pass

#     # Initial request fails with conflict.
#     requests_mocker.post(
#         "https://example.com/api/projects/123/merge_requests",
#         status_code=409,
#         json={},
#     )

#     # Then it should try to find the existing MR.
#     requests_mocker.get(
#         "https://example.com/api/projects/123/merge_requests?state=opened&source_branch=some-src&target_branch=some-dest",
#         status_code=200,
#         json=[
#             {
#                 "web_url": "https://example.com/existing-mr",
#                 "labels": ["whatever"],
#                 "iid": 112233,
#             }
#         ],
#     )

#     session = GitlabUpdateSession(merge, run_cmd=run_cmd_ok, updates=[])

#     # It should fail
#     with pytest.raises(GitlabException) as excinfo:
#         session.ensure_merge_request_exists()

#     # It should tell us why
#     assert (
#         "An existing merge request https://example.com/existing-mr was found, "
#         "but it was apparently not created by mirror-tool! Refusing to update."
#     ) in str(excinfo.value)


# def test_update_not_found(monkeypatch, requests_mocker: requests_mock.Mocker):
#     """GitlabSession fails to update MR if existing MR can't be found."""

#     monkeypatch.setenv("GITLAB_MIRROR_TOKEN", "abc123-not-a-real-token")

#     merge = GitlabMerge(
#         api_v4_url="https://example.com/api",
#         project_id=123,
#         push_url="https://example.com/push",
#         src="some-src",
#         dest="some-dest",
#     )

#     def run_cmd_ok(*args, **kwargs):
#         pass

#     # Initial request fails with conflict.
#     requests_mocker.post(
#         "https://example.com/api/projects/123/merge_requests",
#         status_code=409,
#         json={},
#     )

#     # Then it should try to find the existing MR.
#     requests_mocker.get(
#         "https://example.com/api/projects/123/merge_requests?state=opened&source_branch=some-src&target_branch=some-dest",
#         status_code=200,
#         # unexpected: found no MR
#         json=[],
#     )

#     session = GitlabUpdateSession(merge, run_cmd=run_cmd_ok, updates=[])

#     # It should fail
#     with pytest.raises(GitlabException) as excinfo:
#         session.ensure_merge_request_exists()

#     # It should tell us why
#     assert (
#         "Failed to create MR due to conflict, "
#         "but also failed to locate an existing MR!"
#     ) in str(excinfo.value)
