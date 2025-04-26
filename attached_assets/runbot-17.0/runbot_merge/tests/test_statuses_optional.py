from utils import Commit, to_pr


def test_basic(env, project, make_repo, users, setreviewers, config):
    repository = make_repo('repo')
    env['runbot_merge.repository'].create({
        'project_id': project.id,
        'name': repository.name,
        'status_ids': [(0, 0, {'context': 'l/int', 'prs': 'optional'})]
    })
    setreviewers(*project.repo_ids)
    env['runbot_merge.events_sources'].create({'repository': repository.name})

    with repository:
        m = repository.make_commits(None, Commit('root', tree={'a': '1'}), ref='heads/master')

        repository.make_commits(m, Commit('pr', tree={'a': '2'}), ref='heads/change')
        pr = repository.make_pr(target='master', title='super change', head='change')
    env.run_crons()

    # if an optional status is never received then the PR is valid
    pr_id = to_pr(env, pr)
    assert pr_id.state == 'validated'

    # If a run has started, then the PR is pending (not considered valid), this
    # limits the odds of merging a PR even though it's not valid, as long as the
    # optional status starts running before all the required statuses arrive
    # (with a success result).
    with repository:
        repository.post_status(pr.head, 'pending', 'l/int')
    env.run_crons()
    assert pr_id.state == 'opened'

    # If the status fails, then the PR is rejected.
    with repository:
        repository.post_status(pr.head, 'failure', 'l/int')
    env.run_crons()
    assert pr_id.state == 'opened'

    # re-run the job / fix the PR
    with repository:
        repository.post_status(pr.head, 'pending', 'l/int')
    env.run_crons()
    assert pr_id.state == 'opened'

    with repository:
        repository.post_status(pr.head, 'success', 'l/int')
    env.run_crons()
    assert pr_id.state == 'validated'
