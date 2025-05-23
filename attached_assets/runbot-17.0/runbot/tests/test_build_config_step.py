# -*- coding: utf-8 -*-
import datetime
from unittest.mock import patch, mock_open
from odoo import Command, fields
from odoo.tools import mute_logger
from odoo.exceptions import UserError
from odoo.addons.runbot.common import RunbotException
from .common import RunbotCase
from ..common import markdown_unescape

class TestBuildConfigStepCommon(RunbotCase):
    def setUp(self):
        super().setUp()

        self.Build = self.env['runbot.build']
        self.ConfigStep = self.env['runbot.build.config.step']
        self.Config = self.env['runbot.build.config']

        self.server_commit = self.Commit.create({
            'name': 'dfdfcfcf',
            'repo_id': self.repo_server.id
        })
        self.parent_build = self.Build.create({
            'params_id': self.base_params.copy({'commit_link_ids': [(0, 0, {'commit_id': self.server_commit.id})]}).id,
            'local_result': 'ok',
        })
        self.start_patcher('find_patcher', 'odoo.addons.runbot.common.find', 0)
        self.start_patcher('findall_patcher', 'odoo.addons.runbot.models.build.BuildResult._parse_config', {})


class TestCodeowner(TestBuildConfigStepCommon):
    def setUp(self):
        super().setUp()
        self.config_step = self.ConfigStep.create({
            'name': 'test_codeowner',
            'job_type': 'codeowner',
            'fallback_reviewer': 'codeowner-team',
        })
        self.child_config = self.Config.create({'name': 'test_config'})
        self.config_step.create_config_ids = [self.child_config.id]
        self.team1 = self.env['runbot.team'].create({'name': "Team1", 'github_team': "team_01"})
        self.team2 = self.env['runbot.team'].create({'name': "Team2", 'github_team': "team_02"})
        self.env['runbot.codeowner'].create({'github_teams': 'team_py', 'project_id': self.project.id, 'regex': '.*.py'})
        self.env['runbot.codeowner'].create({'github_teams': 'team_js', 'project_id': self.project.id, 'regex': '.*.js'})
        self.server_commit.name = 'dfdfcfcf'

    def test_codeowner_is_base(self):
        self.dev_bundle.is_base = True
        self.config_step._run_codeowner(self.parent_build)
        self.assertEqual(self.parent_build.log_ids.mapped('message'), [
            'Skipping base bundle',
        ])
        self.assertEqual(self.parent_build.local_result, 'ok')

    def test_codeowner_check_limits(self):
        self.parent_build.params_id.commit_link_ids[0].file_changed = 451
        self.parent_build.params_id.commit_link_ids[0].base_ahead = 51
        self.config_step._run_codeowner(self.parent_build)
        self.assertEqual(self.parent_build.log_ids.mapped('message'), [
            'Limit reached: dfdfcfcf has more than 50 commit (51) and will be skipped. Contact runbot team to increase your limit if it was intended',
            'Limit reached: dfdfcfcf has more than 450 modified files (451) and will be skipped. Contact runbot team to increase your limit if it was intended',
        ])
        self.assertEqual(self.parent_build.local_result, 'ko')

    def test_codeowner_draft(self):
        self.dev_pr.draft = True
        self.config_step._run_codeowner(self.parent_build)
        self.assertEqual(self.parent_build.log_ids.mapped('message'), [
            'Some pr are draft, skipping: 1234'
        ])
        self.assertEqual(self.parent_build.local_result, 'warn')

    def test_codeowner_draft_closed(self):
        self.dev_pr.draft = True
        self.dev_pr.alive = False
        self.assertEqual(self.parent_build.local_result, 'ok')

    def test_codeowner_forwardpot(self):
        self.dev_pr.pr_author = 'fw-bot'
        self.config_step._run_codeowner(self.parent_build)
        self.assertEqual(self.parent_build.log_ids.mapped('message'), [
            'Ignoring forward port pull request: 1234'
        ])
        self.assertEqual(self.parent_build.local_result, 'ok')

    def test_codeowner_invalid_target(self):
        self.dev_pr.target_branch_name = 'master-other-dev-branch'
        self.config_step._run_codeowner(self.parent_build)
        self.assertEqual(self.parent_build.log_ids.mapped('message'), [
            'Some pr have an invalid target: 1234'
        ])
        self.assertEqual(self.parent_build.local_result, 'ko')

    def test_codeowner_pr_duplicate(self):
        second_pr = self.Branch.create({
            'name': '1235',
            'is_pr': True,
            'remote_id': self.remote_server.id,
            'target_branch_name': self.dev_bundle.base_id.name,
            'pull_head_remote_id': self.remote_server.id,
            'pull_head_name': f'{self.remote_server.owner}:{self.dev_branch.name}',
        })
        self.assertEqual(second_pr.bundle_id.id, self.dev_bundle.id)
        self.config_step._run_codeowner(self.parent_build)
        self.assertEqual(self.parent_build.log_ids.mapped('message'), [
            "More than one open pr in this bundle for server: ['1234', '1235']"
        ])
        self.assertEqual(self.parent_build.local_result, 'ko')

    def test_get_module(self):
        self.assertEqual(self.repo_server.addons_paths, 'addons,core/addons')
        self.assertEqual('module1', self.repo_server._get_module('server/core/addons/module1/some/file.py'))
        self.assertEqual('module1', self.repo_server._get_module('server/addons/module1/some/file.py'))
        self.assertEqual('module_addons', self.repo_addons._get_module('addons/module_addons/some/file.py'))
        self.assertEqual(None, self.repo_server._get_module('server/core/module1/some/file.py'))
        self.assertEqual(None, self.repo_server._get_module('server/core/module/some/file.py'))

    def test_codeowner_regex_multiple(self):
        self.diff = 'file.js\nfile.py\nfile.xml'
        self.config_step._run_codeowner(self.parent_build)
        messages = self.parent_build.log_ids.mapped('message')
        self.assertEqual(messages[1], 'Checking 2 codeowner regexed on 3 files')
        self.assertEqual(markdown_unescape(messages[2]), 'Adding team_js to reviewers for file [server/file.js](https://False/blob/dfdfcfcf/file.js)')
        self.assertEqual(markdown_unescape(messages[3]), 'Adding team_py to reviewers for file [server/file.py](https://False/blob/dfdfcfcf/file.py)')
        self.assertEqual(markdown_unescape(messages[4]), 'Adding codeowner-team to reviewers for file [server/file.xml](https://False/blob/dfdfcfcf/file.xml)')
        self.assertEqual(markdown_unescape(messages[5]), 'Requesting review for pull request [base/server:1234](https://example.com/base/server/pull/1234): codeowner-team, team_js, team_py')
        self.assertEqual(self.dev_pr.reviewers, 'codeowner-team,team_js,team_py')

    def test_codeowner_regex_some_already_on(self):
        self.diff = 'file.js\nfile.py\nfile.xml'
        self.dev_pr.reviewers = 'codeowner-team,team_js'
        self.config_step._run_codeowner(self.parent_build)
        messages = self.parent_build.log_ids.mapped('message')
        self.assertEqual(markdown_unescape(messages[5]), 'Requesting review for pull request [base/server:1234](https://example.com/base/server/pull/1234): team_py')

    def test_codeowner_regex_all_already_on(self):
        self.diff = 'file.js\nfile.py\nfile.xml'
        self.dev_pr.reviewers = 'codeowner-team,team_js,team_py'
        self.config_step._run_codeowner(self.parent_build)
        messages = self.parent_build.log_ids.mapped('message')
        self.assertEqual(messages[5], 'All reviewers are already on pull request [base/server:1234](https://example.com/base/server/pull/1234)')

    def test_codeowner_author_in_team(self):
        self.diff = 'file.js\nfile.py\nfile.xml'
        self.team1.github_team = 'team_py'
        self.team1.github_logins = 'some_member,another_member'
        self.team1.skip_team_pr = True
        self.dev_pr.pr_author = 'some_member'
        self.config_step._run_codeowner(self.parent_build)
        messages = self.parent_build.log_ids.mapped('message')
        self.assertEqual(markdown_unescape(messages[5]), "Skipping teams ['team_py'] since author is part of the team members")
        self.assertEqual(markdown_unescape(messages[6]), 'Requesting review for pull request [base/server:1234](https://example.com/base/server/pull/1234): codeowner-team, team_js')
        self.assertEqual(self.dev_pr.reviewers, 'codeowner-team,team_js,team_py')

    def test_codeowner_ownership_base(self):
        module1 = self.env['runbot.module'].create({'name': "module1"})
        self.env['runbot.module.ownership'].create({'team_id': self.team1.id, 'module_id': module1.id})
        self.diff = '\n'.join([
            'core/addons/module1/some/file.py',
        ])
        self.config_step._run_codeowner(self.parent_build)
        messages = self.parent_build.log_ids.mapped('message')
        self.assertEqual(
            markdown_unescape(messages[2]), 
            'Adding team_01, team_py to reviewers for file [server/core/addons/module1/some/file.py](https://False/blob/dfdfcfcf/core/addons/module1/some/file.py)'
        )

    def test_codeowner_ownership_fallback(self):
        module1 = self.env['runbot.module'].create({'name': "module1"})
        self.env['runbot.module.ownership'].create({'team_id': self.team1.id, 'module_id': module1.id, 'is_fallback': True})
        self.diff = '\n'.join([
            'core/addons/module1/some/file.py',
        ])
        self.config_step._run_codeowner(self.parent_build)
        messages = self.parent_build.log_ids.mapped('message')
        self.assertEqual(
            markdown_unescape(messages[2]), 
            'Adding team_py to reviewers for file [server/core/addons/module1/some/file.py](https://False/blob/dfdfcfcf/core/addons/module1/some/file.py)'
        )

    def test_codeowner_ownership(self):
        module1 = self.env['runbot.module'].create({'name': "module1"})
        module2 = self.env['runbot.module'].create({'name': "module2"})
        self.env['runbot.module.ownership'].create({'team_id': self.team1.id, 'module_id': module1.id})
        self.env['runbot.module.ownership'].create({'team_id': self.team2.id, 'module_id': module2.id})
        self.diff = '\n'.join([
            'core/addons/module1/some/file.py',
            'core/addons/module2/some/file.ext',
            'core/addons/module3/some/file.js',
            'core/addons/module4/some/file.txt',
        ])
        self.config_step._run_codeowner(self.parent_build)
        messages = [markdown_unescape(message) for message in self.parent_build.log_ids.mapped('message')]
        self.assertEqual(messages, [
            'PR [base/server:1234](https://example.com/base/server/pull/1234) found for repo **server**',
            'Checking 2 codeowner regexed on 4 files',
            'Adding team_01, team_py to reviewers for file [server/core/addons/module1/some/file.py](https://False/blob/dfdfcfcf/core/addons/module1/some/file.py)',
            'Adding team_02 to reviewers for file [server/core/addons/module2/some/file.ext](https://False/blob/dfdfcfcf/core/addons/module2/some/file.ext)',
            'Adding team_js to reviewers for file [server/core/addons/module3/some/file.js](https://False/blob/dfdfcfcf/core/addons/module3/some/file.js)',
            'Adding codeowner-team to reviewers for file [server/core/addons/module4/some/file.txt](https://False/blob/dfdfcfcf/core/addons/module4/some/file.txt)',
            'Requesting review for pull request [base/server:1234](https://example.com/base/server/pull/1234): codeowner-team, team_01, team_02, team_js, team_py'
        ])

    def test_codeowner___init__log(self):
        module1 = self.env['runbot.module'].create({'name': "module1"})
        self.env['runbot.module.ownership'].create({'team_id': self.team1.id, 'module_id': module1.id})
        self.diff = '\n'.join([
            'core/addons/module1/some/__init__.py',
        ])
        self.config_step._run_codeowner(self.parent_build)
        logs = self.parent_build.log_ids
        print
        self.assertEqual(
            logs[2]._markdown(),
            'Adding team_01, team_py to reviewers for file <a href="https://False/blob/dfdfcfcf/core/addons/module1/some/__init__.py">server/core/addons/module1/some/__init__.py</a>',
            '__init__.py should not be replaced by <ins>init</ins>.py'
        )

class TestBuildConfigStepRestore(TestBuildConfigStepCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.restore_config_step = cls.env['runbot.build.config.step'].create({
            'name': 'restore',
            'job_type': 'restore',
        })
        cls.restore_config = cls.env['runbot.build.config'].create({
            'name': 'Restore',
            'step_order_ids': [
                (0, 0, {'sequence': 10, 'step_id': cls.restore_config_step.id}),
            ],
        })

    def test_restore(self):
        # setup master branch
        master_batch = self.master_bundle._force()
        with mute_logger('odoo.addons.runbot.models.batch'):
            master_batch._process()
        reference_slot = master_batch.slot_ids
        trigger = reference_slot.trigger_id
        self.assertEqual(trigger.name, 'Server trigger', 'Just checking that we have a single slot')
        reference_build = reference_slot.build_id
        self.env['runbot.database'].create({
            'build_id': reference_build.id,
            'name': f'{reference_build.dest}-suffix',
        })
        reference_build.local_state = 'done'
        reference_build.local_result = 'ok'

        # custom trigger
        config_data = {
                'dump_trigger_id': trigger.id,
                'dump_suffix': 'suffix',
            }
        self.env['runbot.bundle.trigger.custom'].create({
            'bundle_id': self.dev_bundle.id,
            'config_id': self.restore_config.id,
            'trigger_id': trigger.id,
            'config_data': config_data,
        })

        # create dev build
        dev_batch = self.dev_bundle._force()
        with mute_logger('odoo.addons.runbot.models.batch'):
            dev_batch._process()
        dev_batch.base_reference_batch_id = master_batch  # not tested, this is not the purpose of this test
        dev_build = dev_batch.slot_ids.build_id
        self.assertEqual(dev_build.params_id.config_data, config_data)

        docker_params = self.restore_config_step._run_restore(dev_build)
        cmds = docker_params['cmd'].split(' && ')
        self.assertEqual(f'wget https://False/runbot/static/build/{reference_build.dest}/logs/{reference_build.dest}-suffix.zip', cmds[2])
        self.assertEqual(f'psql -q {dev_build.dest}-suffix < dump.sql', cmds[8])
        self.called=True



class TestBuildConfigStepCreate(TestBuildConfigStepCommon):

    def setUp(self):
        super().setUp()
        self.config_step = self.ConfigStep.create({
            'name': 'test_step',
            'job_type': 'create_build',
            'number_builds': 2,
        })
        self.child_config = self.Config.create({'name': 'test_config'})
        self.config_step.create_config_ids = [self.child_config.id]

    def test_config_step_create_results(self):
        """ Test child builds are taken into account"""

        self.config_step._run_create_build(self.parent_build)
        self.assertEqual(len(self.parent_build.children_ids), 2, 'Two sub-builds should have been generated')

        # check that the result will be ignored by parent build
        for child_build in self.parent_build.children_ids:
            self.assertFalse(child_build.orphan_result)
            child_build.local_result = 'ko'
            self.assertEqual(child_build.global_result, 'ko')


        self.assertEqual(self.parent_build.global_result, 'ko')

    def test_config_step_create(self):
        """ Test the config step of type create """
        self.config_step.make_orphan = True
        self.config_step._run_create_build(self.parent_build)
        self.assertEqual(len(self.parent_build.children_ids), 2, 'Two sub-builds should have been generated')

        # check that the result will be ignored by parent build
        for child_build in self.parent_build.children_ids:
            self.assertTrue(child_build.orphan_result, 'An orphan result config step should mark the build as orphan_result')
            child_build.local_result = 'ko'
            # child_build._update_:globals()

        self.assertEqual(self.parent_build.global_result, 'ok')

    def test_config_step_create_child_data(self):
        """ Test the config step of type create """
        self.config_step.number_builds = 5
        json_config = {'child_data': [{'extra_params': '-i m1'}, {'extra_params': '-i m2'}]}
        self.parent_build = self.Build.create({
            'params_id': self.base_params.create({
                'version_id': self.version_13.id,
                'project_id': self.project.id,
                'config_id': self.default_config.id,
                'config_data': json_config,
            }).id,
        })

        self.config_step._run_create_build(self.parent_build)
        self.assertEqual(len(self.parent_build.children_ids), 10, '10 build should have been generated')

        # check that the result will be ignored by parent build
        for child_build in self.parent_build.children_ids:
            self.assertTrue(child_build.config_id, self.child_config)

    def test_config_step_create_child_data_unique(self):
        """ Test the config step of type create """
        json_config = {'child_data': {'extra_params': '-i m1'}, 'number_build': 5}
        self.parent_build = self.Build.create({
            'params_id': self.base_params.create({
                'version_id': self.version_13.id,
                'project_id': self.project.id,
                'config_id': self.default_config.id,
                'config_data': json_config,
            }).id,
        })

        self.config_step._run_create_build(self.parent_build)
        self.assertEqual(len(self.parent_build.children_ids), 5, '5 build should have been generated')

        # check that the result will be ignored by parent build
        for child_build in self.parent_build.children_ids:
            self.assertTrue(child_build.config_id, self.child_config)

    def test_config_step_create_child_data_with_config(self):
        """ Test the config step of type create """

        test_config_1 = self.Config.create({'name': 'test_config1'})
        test_config_2 = self.Config.create({'name': 'test_config2'})

        self.config_step.number_builds = 5
        json_config = {'child_data': [{'extra_params': '-i m1', 'config_id': test_config_1.id}, {'config_id': test_config_2.id}]}
        self.parent_build = self.Build.create({
            'params_id': self.base_params.create({
                'version_id': self.version_13.id,
                'project_id': self.project.id,
                'config_id': self.default_config.id,
                'config_data': json_config,
            }).id,
        })

        self.config_step._run_create_build(self.parent_build)
        self.assertEqual(len(self.parent_build.children_ids), 10, '10 build should have been generated')
        self.assertEqual(len(self.parent_build.children_ids.filtered(lambda b: b.config_id == test_config_1)), 5)
        self.assertEqual(len(self.parent_build.children_ids.filtered(lambda b: b.config_id == test_config_2)), 5)




class TestBuildConfigStep(TestBuildConfigStepCommon):

    def test_config_step_raises(self):
        """ Test a config raises when run step position is wrong"""

        run_step = self.ConfigStep.create({
            'name': 'run_step',
            'job_type': 'run_odoo',
        })

        create_step = self.ConfigStep.create({
            'name': 'test_step',
            'job_type': 'create_build',
        })

        config = self.Config.create({'name': 'test_config'})

        # test that the run_odoo step has to be the last one
        with self.assertRaises(UserError):
            config.write({
                 'step_order_ids': [
                     (0, 0, {'sequence': 10, 'step_id': run_step.id}),
                     (0, 0, {'sequence': 15, 'step_id': create_step.id}),
                 ]
             })

        # test that the run_odoo step should be preceded by an install step
        with self.assertRaises(UserError):
            config.write({
                'step_order_ids': [
                    (0, 0, {'sequence': 15, 'step_id': run_step.id}),
                    (0, 0, {'sequence': 10, 'step_id': create_step.id}),
                ]
            })

    def test_config_step_copy(self):
        """ Test a config copy with step_order_ids """

        install_step = self.ConfigStep.create({
            'name': 'install_step',
            'job_type': 'install_odoo'
        })

        run_step = self.ConfigStep.create({
            'name': 'run_step',
            'job_type': 'run_odoo',
        })

        create_step = self.ConfigStep.create({
            'name': 'test_step',
            'job_type': 'create_build',
        })

        config = self.Config.create({'name': 'test_config'})
        StepOrder = self.env['runbot.build.config.step.order']
        # Creation order is impoortant to reproduce the Odoo copy bug/feature :-)
        StepOrder.create({'sequence': 15, 'step_id': run_step.id, 'config_id': config.id})
        StepOrder.create({'sequence': 10, 'step_id': create_step.id, 'config_id': config.id})
        StepOrder.create({'sequence': 12, 'step_id': install_step.id, 'config_id': config.id})

        dup_config = config.copy()
        self.assertEqual(dup_config.step_order_ids.mapped('step_id'), config.step_order_ids.mapped('step_id'))

    @patch('odoo.addons.runbot.models.build.BuildResult._checkout')
    def test_coverage(self, mock_checkout):

        config_step = self.ConfigStep.create({
            'name': 'coverage',
            'job_type': 'install_odoo',
            'coverage': True
        })

        def docker_run(cmd, log_path, *args, **kwargs):
            self.assertEqual(cmd.pres, [['sudo', 'pip3', 'install', '-r', 'server/requirements.txt']])
            self.assertEqual(cmd.cmd[:10], ['python3', '-m', 'coverage', 'run', '--branch', '--source', '/data/build', '--omit', '*__manifest__.py', 'server/server.py'])
            self.assertIn(['python3', '-m', 'coverage', 'html', '-d', '/data/build/coverage', '--ignore-errors'], cmd.posts)
            self.assertIn(['python3', '-m', 'coverage', 'xml', '-o', '/data/build/logs/coverage.xml', '--ignore-errors'], cmd.posts)
            self.assertEqual(log_path, 'dev/null/logpath')

        self.patchers['docker_run'].side_effect = docker_run
        config_step._run_install_odoo(self.parent_build)

    @patch('odoo.addons.runbot.models.build.BuildResult._checkout')
    def test_dump(self, mock_checkout):
        config_step = self.ConfigStep.create({
            'name': 'all',
            'job_type': 'install_odoo',
        })

        def docker_run(cmd, log_path, *args, **kwargs):
            dest = self.parent_build.dest
            self.assertEqual(cmd.cmd[:2], ['python3', 'server/server.py'])
            self.assertEqual(cmd.finals[0], ['pg_dump', '%s-all' % dest, '>', '/data/build/logs/%s-all//dump.sql' % dest])
            self.assertEqual(cmd.finals[1], ['cp', '-r', '/data/build/datadir/filestore/%s-all' % dest, '/data/build/logs/%s-all//filestore/' % dest])
            self.assertEqual(cmd.finals[2], ['cd', '/data/build/logs/%s-all/' % dest, '&&', 'zip', '-rmq9', '/data/build/logs/%s-all.zip' % dest, '*'])
            self.assertEqual(log_path, 'dev/null/logpath')

        self.patchers['docker_run'].side_effect = docker_run

        config_step._run_install_odoo(self.parent_build)

    def get_test_tags(self, params):
        cmds = params['cmd'].build().split(' && ')
        self.assertEqual(cmds[1].split(' server/server.py')[0], 'python3')
        return cmds[1].split('--test-tags ')[1].split(' ')[0]

    @patch('odoo.addons.runbot.models.build.BuildResult._parse_config')
    @patch('odoo.addons.runbot.models.build.BuildResult._checkout')
    def test_install_tags(self, mock_checkout, parse_config):
        parse_config.return_value = {'--test-enable', '--test-tags'}
        config_step = self.ConfigStep.create({
            'name': 'all',
            'job_type': 'install_odoo',
            'enable_auto_tags': False,
            'test_tags': '/module,:class.method',
        })
        self.env['runbot.build.error'].create({
            'content': 'foo',
            'random': True,
            'test_tags': ':otherclass.othertest'
        })
        params = config_step._run_install_odoo(self.parent_build)
        tags = self.get_test_tags(params)
        self.assertEqual(tags, '/module,:class.method')

        config_step.enable_auto_tags = True
        params = config_step._run_install_odoo(self.parent_build)
        tags = self.get_test_tags(params)
        self.assertEqual(tags, '/module,:class.method,-:otherclass.othertest')

    @patch('odoo.addons.runbot.models.build.BuildResult._parse_config')
    @patch('odoo.addons.runbot.models.build.BuildResult._checkout')
    def test_install_custom_tags(self, mock_checkout, parse_config):
        parse_config.return_value = {'--test-enable', '--test-tags'}
        config_step = self.ConfigStep.create({
            'name': 'all',
            'job_type': 'install_odoo',
            'enable_auto_tags': True,
        })
        self.env['runbot.build.error'].create({
            'content': 'foo',
            'random': True,
            'test_tags': ':otherclass.othertest'
        })

        child = self.parent_build._add_child({'config_data': {'test_tags': '-at_install,/module1,/module2'}})

        params = config_step._run_install_odoo(child)
        tags = self.get_test_tags(params)
        self.assertEqual(tags, '-at_install,/module1,/module2,-:otherclass.othertest')


    @patch('odoo.addons.runbot.models.build.BuildResult._checkout')
    def test_db_name(self, mock_checkout):
        config_step = self.ConfigStep.create({
            'name': 'default',
            'job_type': 'install_odoo',
            'custom_db_name': 'custom',
        })
        call_count = 0
        assert_db_name = 'custom'

        def docker_run(cmd, log_path, *args, **kwargs):
            db_sufgfix = cmd.cmd[cmd.index('-d')+1].split('-')[-1]
            self.assertEqual(db_sufgfix, assert_db_name)
            nonlocal call_count
            call_count += 1

        self.patchers['docker_run'].side_effect = docker_run

        config_step._run_step(self.parent_build)()

        assert_db_name = 'custom_build'
        parent_build_params = self.parent_build.params_id.copy({'config_data': {'db_name': 'custom_build'}})
        parent_build = self.parent_build.copy({'params_id': parent_build_params.id})
        config_step._run_step(parent_build)()

        config_step = self.ConfigStep.create({
            'name': 'run_test',
            'job_type': 'run_odoo',
            'custom_db_name': 'custom',
        })
        config_step._run_step(parent_build)()

        self.assertEqual(call_count, 3)

    @patch('odoo.addons.runbot.models.build.BuildResult._checkout')
    def test_run_python(self, mock_checkout):
        """minimal test for python steps. Also test that `-d` in cmd creates a database"""
        test_code = """cmd = build._cmd()
cmd += ['-d', 'test_database']
docker_params = dict(cmd=cmd)
        """
        config_step = self.ConfigStep.create({
            'name': 'default',
            'job_type': 'python',
            'python_code': test_code,
        })

        def docker_run(cmd, *args, **kwargs):
            run_cmd = cmd.build()
            self.assertIn('-d test_database', run_cmd)

        self.patchers['docker_run'].side_effect = docker_run
        config_step._run_step(self.parent_build)()
        self.patchers['docker_run'].assert_called_once()
        db = self.env['runbot.database'].search([('name', '=', 'test_database')])
        self.assertEqual(db.build_id, self.parent_build)

    def test_run_python_run(self):
        """minimal test for python steps. Also test that `-d` in cmd creates a database"""
        test_code = """
def run():
    return {'a': 'b'}
"""
        config_step = self.ConfigStep.create({
            'name': 'default',
            'job_type': 'python',
            'python_code': test_code,
        })

        retult = config_step._run_python(self.parent_build)
        self.assertEqual(retult, {'a': 'b'})

    @patch('odoo.addons.runbot.models.build.BuildResult._checkout')
    def test_sub_command(self, mock_checkout):
        config_step = self.ConfigStep.create({
            'name': 'default',
            'job_type': 'install_odoo',
            'sub_command': 'subcommand',
        })
        call_count = 0

        def docker_run(cmd, log_path, *args, **kwargs):
            nonlocal call_count
            sub_command = cmd.cmd[cmd.index('server/server.py')+1]
            self.assertEqual(sub_command, 'subcommand')
            call_count += 1

        self.patchers['docker_run'].side_effect = docker_run
        config_step._run_step(self.parent_build)()

        self.assertEqual(call_count, 1)


class TestMakeResult(RunbotCase):

    def setUp(self):
        super(TestMakeResult, self).setUp()
        self.ConfigStep = self.env['runbot.build.config.step']
        self.Config = self.env['runbot.build.config']
        self.patchers['getmtime'].return_value = 7200
        self.logs = []
        def _log(build, func, message, level='INFO', log_type='runbot', path='runbot'):
            self.logs.append((level, message))

        self.start_patcher('log_patcher', 'odoo.addons.runbot.models.build.BuildResult._log', new=_log)

        self.build = self.Build.create({
            'params_id': self.base_params.id,
        })
        self.config_step = self.ConfigStep.create({
            'name': 'all',
            'job_type': 'install_odoo',
            'test_tags': '/module,:class.method',
        })

    def test_make_result_ok(self):
        file_content = """
Loading stuff
odoo.stuff.modules.loading: Modules loaded.
Some post install stuff
Initiating shutdown
"""
        with patch('builtins.open', mock_open(read_data=file_content)):
            self.config_step._make_results(self.build)
        self.assertEqual(str(self.build.job_end), '1970-01-01 02:00:00')
        self.assertEqual(self.logs, [('INFO', 'Getting results for build %s' % self.build.dest)])
        self.assertEqual(self.build.local_result, 'ok')

    def test_make_result_no_shutdown(self):
        file_content = """
Loading stuff
odoo.stuff.modules.loading: Modules loaded.
Some post install stuff
        """
        with patch('builtins.open', mock_open(read_data=file_content)):
            self.config_step._make_results(self.build)
        self.assertEqual(str(self.build.job_end), '1970-01-01 02:00:00')
        self.assertEqual(self.build.local_result, 'ko')
        self.assertEqual(self.logs, [
            ('INFO', 'Getting results for build %s' % self.build.dest),
            ('ERROR', 'No "Initiating shutdown" found in logs, maybe because of cpu limit.'),
        ])

    def test_make_result_no_loaded(self):
        file_content = """
Loading stuff
"""
        with patch('builtins.open', mock_open(read_data=file_content)):
            self.config_step._make_results(self.build)
        self.assertEqual(str(self.build.job_end), '1970-01-01 02:00:00')
        self.assertEqual(self.build.local_result, 'ko')
        self.assertEqual(self.logs, [
            ('INFO', 'Getting results for build %s' % self.build.dest),
            ('ERROR', 'Modules loaded not found in logs'),
        ])

    def test_make_result_traceback(self):
        file_content = """
Loading stuff
Traceback (most recent call last):
  File "/data/build/odoo/odoo-bin", line 5, in <module>
    import odoo
  File "/data/build/odoo/odoo/__init__.py", line 134, in <module>
    from . import modules
  File "/data/build/odoo/odoo/modules/__init__.py", line 8, in <module>
    from . import db, graph, loading, migration, module, registry, neutralize
  File "/data/build/odoo/odoo/modules/graph.py", line 11, in <module>
    import odoo.tools as tools
  File "/data/build/odoo/odoo/tools/__init__.py", line 25, in <module>
    from .mail import *
  File "/data/build/odoo/odoo/tools/mail.py", line 32, in <module>
    safe_attrs = clean.defs.safe_attrs | frozenset(
AttributeError: module 'lxml.html.clean' has no attribute 'defs'
2024-05-14 09:54:22,692 17 INFO dbname path.to.test: aaa
"""
        with patch('builtins.open', mock_open(read_data=file_content)):
            self.config_step._make_results(self.build)
        self.assertEqual(str(self.build.job_end), '1970-01-01 02:00:00')
        self.assertEqual(self.build.local_result, 'ko')
        expected = """Traceback found in logs:
Traceback (most recent call last):
  File "/data/build/odoo/odoo-bin", line 5, in <module>
    import odoo
  File "/data/build/odoo/odoo/__init__.py", line 134, in <module>
    from . import modules
  File "/data/build/odoo/odoo/modules/__init__.py", line 8, in <module>
    from . import db, graph, loading, migration, module, registry, neutralize
  File "/data/build/odoo/odoo/modules/graph.py", line 11, in <module>
    import odoo.tools as tools
  File "/data/build/odoo/odoo/tools/__init__.py", line 25, in <module>
    from .mail import *
  File "/data/build/odoo/odoo/tools/mail.py", line 32, in <module>
    safe_attrs = clean.defs.safe_attrs | frozenset(
AttributeError: module 'lxml.html.clean' has no attribute 'defs'"""
        self.assertEqual(self.logs, [
            ('INFO', 'Getting results for build %s' % self.build.dest),
            ('ERROR', expected),
        ])

    def test_make_result_error(self):
        file_content = """
Loading stuff
odoo.stuff.modules.loading: Modules loaded.
Some post install stuff
2024-05-14 09:54:22,692 17 ERROR dbname path.to.test: FAIL: TestClass.test_
Some log
2024-05-14 09:54:22,692 17 ERROR dbname path.to.test: FAIL: TestClass.test2_
Initiating shutdown
"""
        with patch('builtins.open', mock_open(read_data=file_content)):
            self.config_step._make_results(self.build)
        self.assertEqual(str(self.build.job_end), '1970-01-01 02:00:00')
        self.assertEqual(self.build.local_result, 'ko')
        self.assertEqual(self.logs, [
            ('INFO', 'Getting results for build %s' % self.build.dest),
            ('ERROR', """Error found in logs:
2024-05-14 09:54:22,692 17 ERROR dbname path.to.test: FAIL: TestClass.test_
2024-05-14 09:54:22,692 17 ERROR dbname path.to.test: FAIL: TestClass.test2_"""),
        ])

    def test_make_result_warning(self):
        file_content = """
Loading stuff
odoo.stuff.modules.loading: Modules loaded.
Some post install stuff
2019-12-17 17:34:37,692 17 WARNING dbname path.to.test: timeout exceded
Initiating shutdown
"""
        with patch('builtins.open', mock_open(read_data=file_content)):
            self.config_step._make_results(self.build)
        self.assertEqual(str(self.build.job_end), '1970-01-01 02:00:00')
        self.assertEqual(self.build.local_result, 'warn')
        self.assertEqual(self.logs, [
            ('INFO', 'Getting results for build %s' % self.build.dest),
            ('WARNING', 'Warning found in logs')
        ])

        # no log file
        self.logs = []
        self.patchers['isfile'].return_value = False
        self.config_step._make_results(self.build)

        self.assertEqual(self.build.local_result, 'ko')
        self.assertEqual(self.logs, [
            ('INFO', 'Getting results for build %s' % self.build.dest),
            ('ERROR', 'Log file not found at the end of test job')
        ])

    def test_make_result_already_warn(self):
        file_content = """
Loading stuff
odoo.stuff.modules.loading: Modules loaded.
Some post install stuff
Initiating shutdown
"""
        self.patchers['isfile'].return_value = True
        self.build.local_result = 'warn'
        with patch('builtins.open', mock_open(read_data=file_content)):
            self.config_step._make_results(self.build)
        self.assertEqual(self.logs, [
            ('INFO', 'Getting results for build %s' % self.build.dest)
        ])
        self.assertEqual(str(self.build.job_end), '1970-01-01 02:00:00')
        self.assertEqual(self.build.local_result, 'warn')


    @patch('odoo.addons.runbot.models.build_config.ConfigStep._make_odoo_results')
    def test_make_python_result(self, mock_make_odoo_results):
        config_step = self.ConfigStep.create({
            'name': 'all',
            'job_type': 'python',
            'test_tags': '/module,:class.method',
            'python_result_code': """a = 2*5\nreturn_value = {'local_result': 'ok'}"""
        })
        build = self.Build.create({
            'params_id': self.base_params.id,
        })
        build.local_state = 'testing'
        self.patchers['isfile'].return_value = False
        config_step._make_results(build)
        self.assertEqual(build.local_result, 'ok')

        # invalid result code (no return_value set)
        config_step.python_result_code = """a = 2*5\nr = {'a': 'ok'}\nreturn_value = 'ko'"""
        with self.assertRaises(RunbotException):
            config_step._make_results(build)

        # no result defined
        config_step.python_result_code = ""
        def make_warn(build):
            build.local_result = "warn"

        mock_make_odoo_results.side_effect = make_warn
        config_step._make_results(build)
        self.assertEqual(build.local_result, 'warn')

# TODO add generic test to copy_paste _run_* in a python step
