import pytest

from utils import Commit, to_pr


@pytest.fixture
def _setup_statuses(project, repo):
    project.repo_ids.status_ids = [
        (5, 0, 0),
        (0, 0, {'context': 'ci'}),
        # require the lint status on master
        (0, 0, {
            'context': 'lint',
            'branch_filter': [('id', '=', project.branch_ids.id)]
        }),
        (0, 0, {'context': 'pr', 'stagings': False}),
        (0, 0, {'context': 'staging', 'prs': 'ignored'}),
    ]

@pytest.mark.usefixtures('_setup_statuses')
def test_status_applies(env, repo, config):
    """ If branches are associated with a repo status, only those branch should
    require the status on their PRs & stagings
    """
    with repo:
        m = repo.make_commits(None, Commit('root', tree={'a': '1'}), ref='heads/master')

        [c] = repo.make_commits(m, Commit('pr', tree={'a': '2'}), ref='heads/change')
        pr = repo.make_pr(target='master', title="super change", head='change')
    pr_id = to_pr(env, pr)

    for context in ['ci', 'pr', 'lint']:
        assert pr_id.state == 'opened'
        with repo:
            repo.post_status(c, 'success', context)
        env.run_crons(None)
    assert pr_id.state == 'validated'

    with repo:
        pr.post_comment('hansen r+', config['role_reviewer']['token'])
    env.run_crons()

    st = env['runbot_merge.stagings'].search([])
    for context in ['ci', 'lint', 'staging']:
        assert st.state == 'pending'
        with repo:
            repo.post_status('staging.master', 'success', context)
        env.run_crons(None)
    assert st.state == 'success'

@pytest.mark.usefixtures('_setup_statuses')
def test_status_skipped(env, project, repo, config):
    """ Branches not associated with a repo status should not require the status
    on their PRs or stagings
    """
    # add a second branch for which the lint status doesn't apply
    project.write({'branch_ids': [(0, 0, {'name': 'maintenance'})]})
    with repo:
        m = repo.make_commits(None, Commit('root', tree={'a': '1'}), ref='heads/maintenance')

        [c] = repo.make_commits(m, Commit('pr', tree={'a': '2'}), ref='heads/change')
        pr = repo.make_pr(target='maintenance', title="super change", head='change')
    pr_id = to_pr(env, pr)

    for context in ['ci', 'pr']:
        assert pr_id.state == 'opened'
        with repo:
            repo.post_status(c, 'success', context)
        env.run_crons(None)
    assert pr_id.state == 'validated'

    with repo:
        pr.post_comment('hansen r+', config['role_reviewer']['token'])
    env.run_crons()

    st = env['runbot_merge.stagings'].search([])
    for context in ['staging', 'ci']:
        assert st.state == 'pending'
        with repo:
            repo.post_status('staging.maintenance', 'success', context)
        env.run_crons(None)
    assert st.state == 'success'

def test_pseudo_version_tag(env, project, make_repo, setreviewers, config):
    """ Because the last branch in the sequence is "live", if a PR's merged in
    it it's hard to know where it landed in terms of other branches.

    Therefore if a PR is merged in one such branch, tag it using the previous
    branch of the sequence:

    * if that ends with a number, increment the number by 1
    * otherwise add 'post-' prefix (I guess)
    """
    repo = make_repo('repo')
    project.branch_ids.sequence = 1
    project.write({
        'repo_ids': [(0, 0, {'name': repo.name, 'required_statuses': 'ci'})],
        'branch_ids': [
            (0, 0, {'name': '2.0', 'sequence': 11}),
            (0, 0, {'name': '1.0', 'sequence': 21})
        ],
    })
    setreviewers(*project.repo_ids)
    env['runbot_merge.events_sources'].create({'repository': repo.name})

    with repo:
        [m] = repo.make_commits(None, Commit('c1', tree={'a': '1'}), ref='heads/master')
        repo.make_ref('heads/1.0', m)
        repo.make_ref('heads/2.0', m)
        repo.make_ref('heads/bonk', m)

    with repo:
        repo.make_commits(m, Commit('pr1', tree={'b': '1'}), ref='heads/change')
        pr = repo.make_pr(target='master', head='change')
        repo.post_status(pr.ref, 'success', 'ci')
        pr.post_comment('hansen r+', config['role_reviewer']['token'])
    env.run_crons() # should create staging
    pr_id = to_pr(env, pr)
    assert pr_id.state == 'ready'
    assert pr_id.staging_id
    with repo:
        repo.post_status('staging.master', 'success', 'ci')
    env.run_crons() # should merge staging
    assert pr_id.state == 'merged'
    assert pr.labels >= {'2.1'}

    # now the second branch is non-numeric, therefore the label should just be prefixed by "post-"
    project.write({'branch_ids': [(0, 0, {'name': 'bonk', 'sequence': 6})]})
    with repo:
        repo.make_commits(m, Commit('pr2', tree={'c': '1'}), ref='heads/change2')
        pr = repo.make_pr(target='master', head='change2')
        repo.post_status(pr.ref, 'success', 'ci')
        pr.post_comment('hansen r+', config['role_reviewer']['token'])
    env.run_crons() # should create staging
    pr_id = to_pr(env, pr)
    assert pr_id.state == 'ready', pr.comments
    assert pr_id.staging_id
    with repo:
        repo.post_status('staging.master', 'success', 'ci')
    env.run_crons() # should merge staging
    assert pr_id.state == 'merged'
    assert pr.labels >= {'post-bonk'}
