# Syncing `develop` to Feature Branches via Jenkins

This document describes how to automatically merge changes from the `develop` branch into all active `feature/*` branches using Jenkins.

## Problem

When multiple developers work on long-running feature branches, they can drift far from `develop`. Manually merging `develop` into each feature branch is tedious and error-prone.

## Pre-Requirements

Before setting up the Jenkins pipeline, the following credentials and server configurations must be stored in Jenkins.

**Setup checklist:**

- [ ] Virtual machine provisioned (Linux recommended, min. 2 vCPU / 4 GB RAM)
- [ ] Jenkins installed and accessible on the VM (see [Jenkins installation guide](https://www.jenkins.io/doc/book/installing/))
- [ ] Jira Cloud service account created
- [ ] Jira API token generated and available
- [ ] Jira credentials stored in Jenkins (`jira-cloud-credentials`)
- [ ] SMTP credentials stored in Jenkins (`smtp-credentials`)
- [ ] SMTP server configured in Jenkins system settings
- [ ] Mailing list created on the mail server for conflict notifications (e.g. `dev-sync-alerts@example.com`)
- [ ] Bitbucket Cloud repository credentials stored in Jenkins (`bitbucket-credentials-id`)
- [ ] Pipeline repository credentials stored in Jenkins (`pipeline-repo-credentials-id`) for the GitHub Enterprise server hosting the Jenkinsfile
- [ ] Required Jenkins plugins installed (see [Required Jenkins Plugins](#required-jenkins-plugins))

### Jira Cloud Credentials

The pipeline authenticates against Jira Cloud using an **email address and an API token** (not a password). Create a dedicated service account in Jira Cloud for this purpose.

**Steps to generate a Jira API token:**

1. Log in to [https://id.atlassian.com/manage-profile/security/api-tokens](https://id.atlassian.com/manage-profile/security/api-tokens) with the service account.
2. Click *Create API token*, give it a label (e.g. `jenkins-sync`), and copy the token.

**Store in Jenkins:**

1. Go to *Jenkins → Manage Jenkins → Credentials → (global) → Add Credentials*.
2. Kind: **Username with password**
3. **Username:** the service account email address (e.g. `jenkins-sync@example.com`)
4. **Password:** the Jira API token
5. **ID:** `jira-cloud-credentials` *(must match `JIRA_CREDENTIALS` in the Jenkinsfile)*

### Email Server Credentials

The pipeline sends notifications on merge conflicts. The SMTP server and its credentials must be configured in Jenkins.

**Store SMTP credentials in Jenkins:**

1. Go to *Jenkins → Manage Jenkins → Credentials → (global) → Add Credentials*.
2. Kind: **Username with password**
3. **Username:** the sender email address (e.g. `jenkins@example.com`)
4. **Password:** the SMTP password or app password
5. **ID:** `smtp-credentials`

**Configure the mail server in Jenkins:**

1. Go to *Jenkins → Manage Jenkins → System*.
2. Scroll to *E-mail Notification* (or *Extended E-mail Notification* if using the Email Extension plugin).
3. Fill in:
   - **SMTP server:** e.g. `smtp.example.com`
   - **SMTP port:** `587` (STARTTLS) or `465` (SSL)
   - **Use SMTP Authentication:** ✓ — select the `smtp-credentials` credential
   - **Use TLS:** ✓
4. Use *Test configuration* to verify the setup.

## Recommended Approach

A Jenkins pipeline job polls the remote repository every 15 minutes. When it detects new commits on `develop`, it enumerates all feature branches whose name matches the pattern `EALEB-<ticket-number>`, verifies via the Jira API that the ticket is still open, and then merges `develop` into each qualifying branch.

> **Scope:** This pipeline performs **merge operations only**. It does not compile, test, or build the feature branch. Running a build on the feature branch after the merge is the responsibility of the developer.

### Required Jenkins Plugins

| Plugin | Purpose |
| ------ | ------- |
| [Git Plugin](https://plugins.jenkins.io/git/) | Git operations inside pipelines — used for both Bitbucket Cloud and GitHub Enterprise |
| [Git Plugin](https://plugins.jenkins.io/git/) (SCM polling) | Poll Bitbucket Cloud remote every 15 min for changes on `develop` |
| [HTTP Request Plugin](https://plugins.jenkins.io/http_request/) | Query Jira REST API to check ticket status |
| [Credentials Binding Plugin](https://plugins.jenkins.io/credentials-binding/) | Securely inject Bitbucket and Jira credentials into the pipeline |
| [Mailer / Slack Notification](https://plugins.jenkins.io/mailer/) | Notify developers of conflicts |
| [Gitflow Plugin](https://plugins.jenkins.io/gitflow/) _(optional)_ | GitFlow-aware merge operations |

### Branch Naming Convention

Only branches matching the following patterns are considered:

```
feature/EALEB-<ticket-number>
feature/EALEB-<ticket-number>_<comment>
```

Examples: `feature/EALEB-123`, `feature/EALEB-4567`, `feature/EALEB-123_add-login-page`, `feature/EALEB-4567_refactor-api`. Branches with any other naming are ignored entirely.

### How Jenkins Discovers Feature Branches

Jenkins does **not** track "active" branches separately. Instead, the pipeline queries the remote repository at runtime for all branches matching `feature/EALEB-*`:

```bash
git branch -r | grep -E 'origin/feature/EALEB-[0-9]+(_[^[:space:]]*)?$'
```

A branch is included if and only if it **exists on the remote** — meaning a developer has pushed it at least once. Consequences:

- Branches pushed but not yet merged → included ✓
- Branches deleted on the remote (e.g. after merge) → excluded ✓
- Stale/abandoned branches still on the remote → also included unless the Jira ticket is closed (see below)

### Jira Ticket Status Check

Before merging, the pipeline queries the Jira REST API to check the status of the ticket referenced in the branch name. The merge is **skipped** if the ticket is in any of the following statuses:

- `Done`
- `Closed`
- `Resolved`
- `Won't Do`

This prevents syncing into branches that belong to finished or abandoned work, even if the branch was not deleted from the remote.

### Repository Overview

| Repository | Hosting | Purpose |
| ---------- | ------- | ------- |
| Application repository | **Bitbucket Cloud** | Contains `develop` and all `feature/EALEB-*` branches |
| Pipeline repository | **GitHub Enterprise** | Contains the `Jenkinsfile` for this sync job |

### Pipeline Script (`Jenkinsfile`)

The `Jenkinsfile` is **not** stored in the application repository. It is versioned in a dedicated repository on the internal **GitHub Enterprise** server. Jenkins checks out the pipeline definition from GitHub Enterprise before execution.

**Jenkins job configuration (*Pipeline* section):**

- **Definition:** Pipeline script from SCM
- **SCM:** Git
- **Repository URL:** `https://your-github-enterprise.example.com/your-org/jenkins-pipelines.git`
- **Credentials:** `pipeline-repo-credentials-id`
- **Branch:** `*/main`
- **Script Path:** `sync-develop/Jenkinsfile`

The job polls **Bitbucket Cloud** every 15 minutes for changes on `develop`. If new commits are found, the sync runs. See [Polling Configuration](#polling-configuration) below.

```groovy
pipeline {
    agent any

    triggers {
        // Poll the remote every 15 minutes.
        // Runs only when new commits are detected on develop.
        // H/15 spreads load across Jenkins agents (H = hash-based offset).
        pollSCM('H/15 * * * *')
    }

    environment {
        // Bitbucket Cloud — application repository
        BITBUCKET_CREDENTIALS = 'bitbucket-credentials-id'     // App password or token for Bitbucket Cloud
        GIT_REPO_URL          = 'https://bitbucket.org/your-workspace/your-repo.git'
        // GitHub Enterprise — pipeline repository (used by Jenkins SCM checkout, not inside the pipeline itself)
        PIPELINE_CREDENTIALS  = 'pipeline-repo-credentials-id' // Credentials for GitHub Enterprise
        // Jira Cloud
        JIRA_CREDENTIALS      = 'jira-cloud-credentials'       // Email + API token stored in Jenkins
        JIRA_BASE_URL         = 'https://your-jira-instance.atlassian.net'
        // Jira statuses that indicate a ticket is finished — skip these branches
        JIRA_SKIP_STATUSES    = 'Done,Closed,Resolved,Won\'t Do'
        // Notifications
        NOTIFY_EMAIL          = 'dev-sync-alerts@example.com'  // Mailing list for conflict notifications
    }

    stages {
        stage('Checkout develop') {
            steps {
                git branch: 'develop',
                    credentialsId: env.BITBUCKET_CREDENTIALS,
                    url: env.GIT_REPO_URL
            }
        }

        stage('Sync develop → feature branches') {
            steps {
                script {
                    sh 'git fetch --all'

                    // Only consider branches matching feature/EALEB-<number>
                    def rawBranches = sh(
                        script: "git branch -r | grep -E 'origin/feature/EALEB-[0-9]+(_[^[:space:]]*)?\$' | sed 's|  origin/||'",
                        returnStdout: true
                    ).trim()

                    if (!rawBranches) {
                        echo 'No matching feature branches found.'
                        return
                    }

                    def branches = rawBranches.split('\n')
                    def skipStatuses = env.JIRA_SKIP_STATUSES.split(',')

                    withCredentials([usernamePassword(
                        credentialsId: env.JIRA_CREDENTIALS,
                        usernameVariable: 'JIRA_USER',
                        passwordVariable: 'JIRA_TOKEN'
                    )]) {
                        branches.each { branch ->
                            // Extract ticket number, e.g. "feature/EALEB-123" → "EALEB-123"
                            def ticketKey = (branch =~ /EALEB-[0-9]+/)[0]

                            // Query Jira REST API for the ticket status
                            def response = httpRequest(
                                url: "${env.JIRA_BASE_URL}/rest/api/2/issue/${ticketKey}?fields=status",
                                authentication: env.JIRA_CREDENTIALS,
                                validResponseCodes: '200,404'
                            )

                            if (response.status == 404) {
                                echo "Skipping ${branch}: Jira ticket ${ticketKey} not found."
                                return
                            }

                            def issueStatus = readJSON(text: response.content).fields.status.name
                            echo "${ticketKey} status: ${issueStatus}"

                            if (skipStatuses.contains(issueStatus)) {
                                echo "Skipping ${branch}: ticket is '${issueStatus}'."
                                return
                            }

                            // Ticket is open — proceed with merge
                            echo "Merging develop into ${branch}..."
                            def mergeResult = sh(
                                script: """
                                    git checkout ${branch}
                                    git merge origin/develop --no-edit
                                """,
                                returnStatus: true
                            )

                            if (mergeResult == 0) {
                                sh "git push origin ${branch}"
                                echo "Successfully synced develop into ${branch}"
                            } else {
                                sh 'git merge --abort'
                                echo "CONFLICT: Could not merge develop into ${branch}. Manual intervention required."
                            }
                        }
                    }
                }
            }
        }
    }

    post {
        failure {
            mail to: env.NOTIFY_EMAIL,
                 subject: "Jenkins: develop sync encountered conflicts",
                 body: "One or more feature branches could not be automatically synced with develop. Please merge manually."
        }
    }
}
```

## Conflict Handling

- If a merge **succeeds** cleanly, the feature branch is pushed automatically.
- If a merge **fails** (conflict), the merge is aborted and a notification is sent to the team. The developer must resolve the conflict manually.
- **Never force-push** on a developer's feature branch from CI — this can destroy uncommitted work.

## Polling Configuration

Because direct access to Bitbucket Cloud is not available for inbound webhooks from Jenkins, Jenkins uses **SCM polling** instead. Jenkins itself initiates the check — no inbound network access to Jenkins is required from Bitbucket Cloud.

### How It Works

1. Every 15 minutes, Jenkins calls `git ls-remote` against the **Bitbucket Cloud** remote URL.
2. It compares the current SHA of `refs/heads/develop` with the SHA from the previous poll.
3. If the SHA has changed, the pipeline is triggered. If not, nothing happens.
4. The `H/15` cron expression uses a hash-based offset per job to avoid all jobs hitting the remote simultaneously.

### Jenkins Setup

1. No additional plugins are required beyond the standard **[Git Plugin](https://plugins.jenkins.io/git/)**.
2. In the Jenkins job configuration, under *Build Triggers*, enable **Poll SCM**.
3. Set the schedule to `H/15 * * * *`.
4. Ensure the repository URL and credentials are correctly configured under *Source Code Management*.

> **Note:** The `pollSCM` trigger in the Jenkinsfile only takes effect after the first manual build or after saving the job configuration in the Jenkins UI.

## Alternatives

| Alternative | Notes |
| ----------- | ----- |
| **GitHub Actions** | `.github/workflows/sync-develop.yml` with `actions/checkout` and a merge script — no Jenkins needed |
| **GitLab CI** | Use `rules: - if: $CI_COMMIT_BRANCH == "develop"` to trigger sync |
| **Manual PR policy** | Require developers to regularly rebase/merge develop themselves, enforced via branch protection rules |

## Related Documents

- [BRANCHING_STRATEGY.md](BRANCHING_STRATEGY.md)
- [CI_CD_SETUP.md](CI_CD_SETUP.md)
