import xmlrpc.client

import pytest

from utils import Commit, read_tracking_value, matches

# basic udiff / show style patch, updates `b` from `1` to `2`
BASIC_UDIFF = """\
commit 0000000000000000000000000000000000000000
Author: 3 Discos Down <bar@example.org>
Date:   2021-04-24T17:09:14Z

    whop
    
    whop whop

diff --git a/b b/b
index d00491fd7e5b..0cfbf08886fc 100644
--- a/b
+++ b/b
@@ -1,1 +1,1 @@
-1
+2
"""

FORMAT_PATCH_XMO = """\
From 0000000000000000000000000000000000000000 Mon Sep 17 00:00:00 2001
From: 3 Discos Down <bar@example.org>
Date: Sat, 24 Apr 2021 17:09:14 +0000
Subject: [PATCH] [I18N] whop

whop whop
---
 b | 2 +-
 1 file changed, 1 insertion(+), 1 deletion(-)
 
diff --git a/b b/b
index d00491fd7e5b..0cfbf08886fc 100644
--- a/b
+++ b/b
@@ -1,1 +1,1 @@
-1
+2
-- 
2.46.2
"""

# slightly different format than the one I got, possibly because older?
FORMAT_PATCH_MAT = """\
From 3000000000000000000000000000000000000000 Mon Sep 17 00:00:00 2001
From: 3 Discos Down <bar@example.org>
Date: Sat, 24 Apr 2021 17:09:14 +0000
Subject: [PATCH 1/1] [I18N] whop

whop whop
---
 b | 2 +-
 1 file changed, 1 insertion(+), 1 deletion(-)
 
diff --git b b
index d00491fd7e5b..0cfbf08886fc 100644
--- b
+++ b
@@ -1,1 +1,1 @@
-1
+2
-- 
2.34.1
"""


@pytest.fixture(autouse=True)
def _setup(repo):
    with repo:
        [c, _] = repo.make_commits(
            None,
            Commit("a", tree={"a": "1", "b": "1\n"}),
            Commit("b", tree={"a": "2"}),
            ref="heads/master",
        )
        repo.make_ref("heads/x", c)

@pytest.mark.parametrize("group,access", [
    ('base.group_portal', False),
    ('base.group_user', False),
    ('runbot_merge.group_patcher', True),
    ('runbot_merge.group_admin', False),
    ('base.group_system', True),
])
def test_patch_acl(env, project, group, access):
    g = env.ref(group)
    assert g._name == 'res.groups'
    env['res.users'].create({
        'name': 'xxx',
        'login': 'xxx',
        'password': 'xxx',
        'groups_id': [(6, 0, [g.id])],
    })
    env2 = env.with_user('xxx', 'xxx')
    def create():
        return env2['runbot_merge.patch'].create({
            'target': project.branch_ids.id,
            'repository': project.repo_ids.id,
            'patch': BASIC_UDIFF,
        })
    if access:
        create()
    else:
        pytest.raises(xmlrpc.client.Fault, create)\
            .match("You are not allowed to create")

def test_apply_commit(env, project, repo, users):
    with repo:
        [c] = repo.make_commits("x", Commit("c", tree={"b": "2"}, author={
            'name': "Henry Hoover",
            "email": "dustsuckinghose@example.org",
        }), ref="heads/abranch")
        repo.delete_ref('heads/abranch')

    p = env['runbot_merge.patch'].create({
        'target': project.branch_ids.id,
        'repository': project.repo_ids.id,
        'commit': c,
    })

    env.run_crons()

    HEAD = repo.commit('master')
    assert repo.read_tree(HEAD) == {
        'a': '2',
        'b': '2',
    }
    assert HEAD.message == "c"
    assert HEAD.author['name'] == "Henry Hoover"
    assert HEAD.author['email'] == "dustsuckinghose@example.org"
    assert not p.active

    # try to apply a dupe version
    p = env['runbot_merge.patch'].create({
        'target': project.branch_ids.id,
        'repository': project.repo_ids.id,
        'commit': c,
    })

    env.run_crons()

    # the patch should have been rejected since it leads to an empty commit
    NEW_HEAD = repo.commit('master')
    assert NEW_HEAD.id == HEAD.id
    assert not p.active
    assert p.message_ids.mapped('body')[::-1] == [
        '<p>Unstaged direct-application patch created</p>',
        "<p>Patch results in an empty commit when applied, "
        "it is likely a duplicate of a merged commit.</p>",
        "",  # empty message alongside active tracking value
    ]

def test_commit_conflict(env, project, repo, users):
    with repo:
        [c] = repo.make_commits("x", Commit("x", tree={"b": "3"}))
        repo.make_commits("master", Commit("c", tree={"b": "2"}), ref="heads/master", make=False)

    p = env['runbot_merge.patch'].create({
        'target': project.branch_ids.id,
        'repository': project.repo_ids.id,
        'commit': c,
    })

    env.run_crons()

    HEAD = repo.commit('master')
    assert repo.read_tree(HEAD) == {
        'a': '2',
        'b': '2',
    }
    assert not p.active
    assert [(
        m.subject,
        m.body,
        list(map(read_tracking_value, m.tracking_value_ids)),
    )
        for m in reversed(p.message_ids)
    ] == [
        (False, '<p>Unstaged direct-application patch created</p>', []),
        (
            "Unable to apply patch",
            "<pre>Auto-merging b\nCONFLICT (content): Merge conflict in b\n</pre>",
            [],
        ),
        (False, '', [('active', 1, 0)]),
    ]

def test_apply_not_found(env, project, repo, users):
    """ Github can take some time to propagate commits through the network,
    resulting in patches getting not found and killing the application.

    Commits which are not found should just be skipped (and trigger a new
    staging?).
    """
    with repo:
        [c] = repo.make_commits("x", Commit("c", tree={"b": "2"}), ref="heads/abranch")
        repo.delete_ref('heads/abranch')

    p1 = env['runbot_merge.patch'].create({
        'target': project.branch_ids.id,
        'repository': project.repo_ids.id,
        'commit': c,
    })
    # simulate commit which hasn't propagated yet
    p2 = env['runbot_merge.patch'].create({
        'target': project.branch_ids.id,
        'repository': project.repo_ids.id,
        'commit': "0123456789012345678901234567890123456789",
    })

    env.run_crons()

    assert not p1.active
    assert p2.active
    assert p2.message_ids.mapped('body')[::-1] == [
        "<p>Unstaged direct-application patch created</p>",
        matches('''\
<p>Commit 0123456789012345678901234567890123456789 not found</p>
<p>stderr:</p>
<pre>
error: Unable to find 0123456789012345678901234567890123456789 under $repo$
Cannot obtain needed object 0123456789012345678901234567890123456789
error: fetch failed.
</pre>\
'''),
    ]

def test_apply_udiff(env, project, repo, users):
    p = env['runbot_merge.patch'].create({
        'target': project.branch_ids.id,
        'repository': project.repo_ids.id,
        'patch': BASIC_UDIFF,
    })

    env.run_crons()

    HEAD = repo.commit('master')
    assert repo.read_tree(HEAD) == {
        'a': '2',
        'b': '2\n',
    }
    assert HEAD.message == "whop\n\nwhop whop"
    assert HEAD.author['name'] == "3 Discos Down"
    assert HEAD.author['email'] == "bar@example.org"
    assert not p.active


@pytest.mark.parametrize('patch', [
    pytest.param(FORMAT_PATCH_XMO, id='xmo'),
    pytest.param(FORMAT_PATCH_MAT, id='mat'),
    pytest.param(
        FORMAT_PATCH_XMO.replace('\n', '\r\n'),
        id='windows',
    ),
    pytest.param(
        FORMAT_PATCH_XMO.rsplit('-- \n')[0],
        id='no-signature',
    )
])
def test_apply_format_patch(env, project, repo, users, patch):
    p = env['runbot_merge.patch'].create({
        'target': project.branch_ids.id,
        'repository': project.repo_ids.id,
        'patch': patch,
    })

    env.run_crons()

    bot = env['res.users'].browse((1,))
    assert p.message_ids[::-1].mapped(lambda m: (
        m.author_id.display_name,
        m.body,
        list(map(read_tracking_value, m.tracking_value_ids)),
    )) == [
        (p.create_uid.partner_id.display_name, '<p>Unstaged direct-application patch created</p>', []),
        (bot.partner_id.display_name, "", [('active', 1, 0)]),
    ]
    HEAD = repo.commit('master')
    assert repo.read_tree(HEAD) == {
        'a': '2',
        'b': '2\n',
    }
    assert HEAD.message == "[I18N] whop\n\nwhop whop"
    assert HEAD.author['name'] == "3 Discos Down"
    assert HEAD.author['email'] == "bar@example.org"
    assert not p.active

def test_patch_conflict(env, project, repo, users):
    p = env['runbot_merge.patch'].create({
        'target': project.branch_ids.id,
        'repository': project.repo_ids.id,
        'patch': BASIC_UDIFF,
    })
    with repo:
        repo.make_commits('master', Commit('cccombo breaker', tree={'b': '3'}), ref='heads/master', make=False)

    env.run_crons()

    HEAD = repo.commit('master')
    assert HEAD.message == 'cccombo breaker'
    assert repo.read_tree(HEAD) == {
        'a': '2',
        'b': '3',
    }
    assert not p.active
    assert [(
        m.subject,
        m.body,
        list(map(read_tracking_value, m.tracking_value_ids)),
    )
        for m in reversed(p.message_ids)
    ] == [(
        False,
        '<p>Unstaged direct-application patch created</p>',
        [],
    ), (
        "Unable to apply patch",
        matches("$$"),  # feedback from patch can vary
        [],
    ), (
        False, '', [('active', 1, 0)]
    )]

CREATE_FILE_FORMAT_PATCH = """\
From 0000000000000000000000000000000000000000 Mon Sep 17 00:00:00 2001
From: 3 Discos Down <bar@example.org>
Date: Sat, 24 Apr 2021 17:09:14 +0000
Subject: [PATCH] [I18N] whop

whop whop
---
 x | 1 +
 1 file changed, 1 insertion(+)
 create mode 100644 b

diff --git a/x b/x
new file mode 100644
index 000000000000..d00491fd7e5b
--- /dev/null
+++ b/x
@@ -0,0 +1 @@
+1
-- 
2.48.1
"""

CREATE_FILE_SHOW = """\
commit 0000000000000000000000000000000000000000
Author: 3 Discos Down <bar@example.org>
Date:   2021-04-24T17:09:14Z

    [I18N] whop
    
    whop whop

diff --git a/x b/x
new file mode 100644
index 000000000000..d00491fd7e5b
--- /dev/null
+++ b/x
@@ -0,0 +1 @@
+1
"""

@pytest.mark.parametrize('patch', [
    pytest.param(CREATE_FILE_SHOW, id='show'),
    pytest.param(CREATE_FILE_FORMAT_PATCH, id='format-patch'),
])
def test_apply_creation(env, project, repo, users, patch):
    assert repo.read_tree(repo.commit('master')) == {
        'a': '2',
        'b': '1\n',
    }

    env['runbot_merge.patch'].create({
        'target': project.branch_ids.id,
        'repository': project.repo_ids.id,
        'patch': patch,
    })
    # trying to check the list of files doesn't work, even using web_read

    env.run_crons()

    HEAD = repo.commit('master')
    assert repo.read_tree(HEAD) == {
        'a': '2',
        'b': '1\n',
        'x': '1\n',
    }
    assert HEAD.message == "[I18N] whop\n\nwhop whop"
    assert HEAD.author['name'] == "3 Discos Down"
    assert HEAD.author['email'] == "bar@example.org"
