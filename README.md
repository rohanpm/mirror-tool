# mirror-tool

A tool for maintaining Git subtree mirrors.

![GitHub Workflow Status (branch)](https://img.shields.io/github/workflow/status/rohanpm/mirror-tool/CI/main) ![PyPI](https://img.shields.io/pypi/v/mirror-tool) [![Docker Repository on Quay](https://quay.io/repository/rmcgover/mirror-tool/status "Docker Repository on Quay")](https://quay.io/repository/rmcgover/mirror-tool)

<!--TOC-->

- [mirror-tool](#mirror-tool)
  - [Installation](#installation)
  - [Usage](#usage)
    - [`mirror-tool validate-config`](#mirror-tool-validate-config)
    - [`mirror-tool update-local`](#mirror-tool-update-local)
    - [`mirror-tool update`](#mirror-tool-update)
    - [`mirror-tool promote`](#mirror-tool-promote)
  - [Configuration](#configuration)
    - [Jinja context](#jinja-context)
  - [License](#license)

<!--TOC-->

## Installation

Install the `mirror-tool` package from PyPI.

```
pip install mirror-tool
```

## Usage

`mirror-tool` has the following subcommands. Please install the tool and
run with `--help` for complete documentation on the available commands and
options.

### `mirror-tool validate-config`

Verify that `.mirror-tool.yaml` in the current directory, or a specified
configuration file, is valid.

Exits with a 0 exit code if and only if a valid config file was found.

### `mirror-tool update-local`

For each mirror defined in the config file, create a subtree merge commit
updating that mirror.

By default, this will not create any commits if there are no changes to be made.
It can be forced to create a commit by using the `--allow-empty` argument.

### `mirror-tool update`

Perform the same updates as `update-local`, but also push the commit(s) to any
configured remote targets.

Currently, GitLab is the only supported target. See the configuration reference
below for more information about GitLab integration.

When using this command to push to GitLab, it is recommended to run it from
within a GitLab CI/CD pipeline. The command will use predefined environment
variables in the CI environment to determine how to connect to GitLab.
If used in other contexts, it will be necessary to explicitly set many
environment variables.

### `mirror-tool promote`

For any merge requests previously created by `update`, create additional
merge request(s) to promote the same changes to other branch(es) as defined
in config.

This command can be used to implement a multi-tiered deployment/update workflow,
for example:

- Whenever mirrored repos change, create an MR updating them (via `mirror-tool update`), targeting `testing` branch.
- Perform some pre- or post-merge testing on that MR by some means (outside the
  scope of mirror-tool).
- After the MR is submitted to `testing` branch, create a new MR promoting the
  same changes to `stable` branch (via `mirror-tool promote`).

The command only operates on changes previously created via
`mirror-tool update`.

Like `update`, GitLab is currently the only supported target for this command.

## Configuration

`mirror-tool` requires a configuration file. By convention, this should
be placed at `.mirror-tool.yaml` at the top level of your superproject
repository.

The following example demonstrates the available configuration options.

```yaml
# Define the repositories to mirror.
mirror:
- url: https://github.com/org/repo1
  ref: refs/heads/master
  dir: repo1

- url: https://github.com/org/repo2
  ref: refs/heads/main
  dir: repo2

# Git configuration to be applied when mirror-tool creates commits.
# Any arbitrary config can be set, but this is most commonly needed
# just to set the name/email on merge commits.
git_config:
  user.name: "mirror-tool"
  user.email: "noreply@example.com"

# Message for generated commits.
# This is a Jinja template.
commitmsg: |-
  Merge {{commits[0].revision_abbrev}} to {{mirror.dir}}

  {{commits|length}} commit(s) are being merged.

  {% for commit in commits %}
  - {{ commit.revision_abbrev }} {{ commit.subject }}
  {%- endfor %}

# Configures the GitLab merge request integration.
gitlab_merge:
  # If enabled, the update command will create/update a GitLab
  # merge request whenever a mirrored repo is updated.
  enabled: true

  # Token used to authenticate with GitLab.
  #
  # Currently, this token must always be of the format '$SOME_VARIABLE',
  # and the token will be accessed from that environment variable at
  # runtime. If running from a GitLab CI/CD pipeline, this should be
  # set as a protected CI variable.
  token: $GITLAB_MIRROR_TOKEN

  # Source branch used for merge requests.
  # WARNING: update will do force pushes to this branch!
  src: latest

  # Target branch used for merge requests.
  # The following example supposes that the target branch is used
  # to perform some kind of deployment.
  dest: deploy

  # Title for the merge request.
  # This is a Jinja template.
  title: "Deploy changes [{{ datetime_day }}]"

  # Any desired labels to add onto the merge request.
  labels:
  - deploy

  # Description for the merge request.
  # This is a Jinja template.
  description: |-
    Automated update of dependencies generated by
    {{ env.CI_JOB_URL }}.

    Submitting this merge request will trigger a deployment.

  # Comment(s) to be added when a merge request is created or updated.
  # Can be used to ping reviewers.
  # If omitted, comments won't be added.
  # These are Jinja templates.
  comment:
    create: "@some-team: please review and submit."
    update: "@some-team: merge request has been updated, please re-review."

# Configures GitLab promotion between branches.
# A list of (src, dest) branch pairs with other config.
# Most config has the same meaning as in gitlab_merge.
gitlab_promote:
- src: stage
  dest: prod
  title: "Promote from stage to prod [{{datetime_day}}]"
  token: $GITLAB_MIRROR_TOKEN
  labels:
  - promote
  description: |-
    Automated promotion of {{ src_mr.web_url }} to prod.
```

### Jinja context

Some configuration elements are described above as
[Jinja templates](https://jinja.palletsprojects.com/en/3.0.x/templates/).
The following variables are available for use within the templates:

#### `env` (dict)

* All environment variables at the time `mirror-tool` is invoked.
* If running in GitLab CI/CD, can be used to access the
  [CI/CD variables](https://docs.gitlab.com/ee/ci/variables/predefined_variables.html).
* Example: `{{ env.CI_JOB_URL }}` => `https://gitlab.example.com/someteam/somerepo/-/jobs/6366493`

#### `datetime_iso8601` (str)

* Current UTC date/time, in ISO8601 format, with seconds precision.
* Example: `2022-05-10T05:28:26Z`

#### `datetime_minute` (str)

* Current UTC date/time, with minutes precision.
* Example: `2022-05-10 05:28`

#### `datetime_day` (str)

* Current UTC date.
* Example: `2022-05-10`

#### `datetime_week` (str)

* Current UTC year and week of year.
* Example: `2022wk19` for week 19 of 2022.

#### `updates` (list[UpdateInfo]) *(update only)*

In most Jinja contexts for the `update` and `update-local` commands,
this is a list of objects of the following form:

```python
UpdateInfo(
  mirror=Mirror(
    url="https://github.com/rohanpm/mirror-tool",
    ref="refs/heads/main",
    dir="mirror-tool"
  ),

  # Objects representing commits included in the update, starting
  # with the most recent.
  #
  # If there is a large number of commits being handled, some may be
  # elided from this list.
  commits=[
    Commit(
      revision="472b7797518b963f8ab381c39858c18b2b784c2e",
      revision_abbrev="472b779",
      author_name="Rohan McGovern",
      author_email="rohan@mcgovern.id.au",
      author_email_local="rohan",
      author_datetime=datetime.datetime(2022, 5, 26, 0, 24, 37),
      committer_name="Rohan McGovern",
      committer_email="rohan@mcgovern.id.au",
      committer_email_local="rohan",
      committer_datetime=datetime.datetime(2022, 5, 26, 0, 37, 37),
      subject="Raise test coverage to 100%",
      body="Do this, that and some other\nthings as well.",
    ),
    ...,
  ],

  # Total number of commits in the update (may be more than len(commits)
  # if some were elided).
  commit_count=4,

  # Number of commits omitted from 'commits' object.
  # For example, if an update pulled 200 commits, only the most recent 20
  # may appear in 'commits', and this value will be set to 180.
  commit_elided_count=0,
)
```

In the Jinja context for `commitmsg`, as only a single update is being processed,
`updates` is not defined.  Instead, all of the fields shown above under `UpdateInfo`
are directly included onto the context.

#### `src_mr` (dict) *(promote only)*

A merge request object which is now being promoted; i.e. a merge request
previously created by mirror-tool and submitted to one branch, and now
being promoted by mirror-tool to another branch.

The format of this object can be found in the
[GitLab API docs](https://docs.gitlab.com/ee/api/merge_requests.html).

Only available for the `promote` command.

## License

This program is free software: you can redistribute it and/or modify it under the terms of the GNU General Public License as published by the Free Software Foundation, either version 3 of the License, or (at your option) any later version.
