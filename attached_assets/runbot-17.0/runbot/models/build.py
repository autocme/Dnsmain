# -*- coding: utf-8 -*-

import datetime
import getpass
import hashlib
import logging
import pwd
import re
import shutil
import time
import uuid

from collections import defaultdict
from pathlib import Path
from psycopg2 import sql
from psycopg2.extensions import TransactionRollbackError

from ..common import dt2time, now, grep, local_pgadmin_cursor, s2human, dest_reg, os, list_local_dbs, pseudo_markdown, RunbotException, findall, sanitize, markdown_escape
from ..container import docker_stop, docker_state, Command, docker_run, docker_pull
from ..fields import JsonDictField

from odoo import models, fields, api

from odoo.exceptions import ValidationError
from odoo.tools import file_open, file_path
from odoo.tools.safe_eval import safe_eval


_logger = logging.getLogger(__name__)

result_order = ['ok', 'warn', 'ko', 'skipped', 'killed', 'manually_killed']
state_order = ['pending', 'testing', 'waiting', 'running', 'done']

COPY_WHITELIST = [
    "params_id",
    "description",
    "build_type",
    "parent_id",
    "orphan_result",
]

USERUID = os.getuid()
USERNAME = getpass.getuser()

def make_selection(array):
    return [(elem, elem.replace('_', ' ').capitalize()) if isinstance(elem, str) else elem for elem in array]


class BuildParameters(models.Model):
    _name = 'runbot.build.params'
    _description = "All information used by a build to run, should be unique and set on create only"

    # on param or on build?
    # execution parametter
    commit_link_ids = fields.Many2many('runbot.commit.link', copy=True)
    commit_ids = fields.Many2many('runbot.commit', compute='_compute_commit_ids')
    version_id = fields.Many2one('runbot.version', required=True, index=True)
    project_id = fields.Many2one('runbot.project', required=True, index=True)  # for access rights
    trigger_id = fields.Many2one('runbot.trigger', index=True)  # for access rights
    create_batch_id = fields.Many2one('runbot.batch', index=True)
    category = fields.Char('Category', index=True)  # normal vs nightly vs weekly, ...
    dockerfile_id = fields.Many2one('runbot.dockerfile', index=True, default=lambda self: self.env.ref('runbot.docker_default', raise_if_not_found=False))
    skip_requirements = fields.Boolean('Skip requirements.txt auto install')
    # other informations
    extra_params = fields.Char('Extra cmd args')
    config_id = fields.Many2one('runbot.build.config', 'Run Config', required=True,
                                default=lambda self: self.env.ref('runbot.runbot_build_config_default', raise_if_not_found=False), index=True)
    config_data = JsonDictField('Config Data')
    used_custom_trigger = fields.Boolean('Custom trigger was used to generate this build')

    build_ids = fields.One2many('runbot.build', 'params_id')
    builds_reference_ids = fields.Many2many('runbot.build', relation='runbot_build_params_references', copy=True)
    modules = fields.Char('Modules')

    upgrade_to_build_id = fields.Many2one('runbot.build', index=True)  # use to define sources to use with upgrade script
    upgrade_from_build_id = fields.Many2one('runbot.build', index=True)  # use to download db
    dump_db = fields.Many2one('runbot.database', index=True)  # use to define db to download

    fingerprint = fields.Char('Fingerprint', compute='_compute_fingerprint', store=True, index=True)

    slot_ids = fields.One2many('runbot.batch.slot', 'params_id')

    _sql_constraints = [
        ('unique_fingerprint', 'unique (fingerprint)', 'avoid duplicate params'),
    ]

    # @api.depends('version_id', 'project_id', 'extra_params', 'config_id', 'config_data', 'modules', 'commit_link_ids', 'builds_reference_ids')
    def _compute_fingerprint(self):
        for param in self:
            cleaned_vals = {
                'version_id': param.version_id.id,
                'project_id': param.project_id.id,
                'trigger_id': param.trigger_id.id,
                'extra_params': param.extra_params or '',
                'config_id': param.config_id.id,
                'config_data': param.config_data.dict,
                'modules': param.modules or '',
                'commit_link_ids': sorted(param.commit_link_ids.commit_id.ids),
                'builds_reference_ids': sorted(param.builds_reference_ids.ids),
                'upgrade_from_build_id': param.upgrade_from_build_id.id,
                'upgrade_to_build_id': param.upgrade_to_build_id.id,
                'dump_db': param.dump_db.id,
                'dockerfile_id': param.dockerfile_id.id,
                'skip_requirements': param.skip_requirements,
            }
            if param.trigger_id.batch_dependent:
                cleaned_vals['create_batch_id'] = param.create_batch_id.id
            if param.used_custom_trigger:
                cleaned_vals['used_custom_trigger'] = True

            param.fingerprint = hashlib.sha256(str(cleaned_vals).encode('utf8')).hexdigest()

    @api.depends('commit_link_ids')
    def _compute_commit_ids(self):
        for params in self:
            params.commit_ids = params.commit_link_ids.commit_id

    @api.model_create_multi
    def create(self, vals_list):
        records = self.browse()
        for vals in vals_list:
            params = self.new(vals)
            record = self._find_existing(params.fingerprint)
            if record:
                records |= record
            else:
                records |= super().create(self._convert_to_write(params._cache))
        return records

    def _find_existing(self, fingerprint):
        return self.env['runbot.build.params'].search([('fingerprint', '=', fingerprint)], limit=1)

class BuildResult(models.Model):
    # remove duplicate management
    # instead, link between bundle_batch and build
    # kill -> only available from bundle.
    # kill -> actually detach the build from the bundle
    # rebuild: detach and create a new link (a little like exact rebuild),
    # if a build is detached from all bundle, kill it
    # nigktly?

    _name = 'runbot.build'
    _description = "Build"

    _parent_store = True
    _order = 'id desc'
    _rec_name = 'id'

    # all displayed info removed. How to replace that?
    # -> commit corresponding to repo of trigger_id5
    # -> display all?

    params_id = fields.Many2one('runbot.build.params', required=True, index=True, auto_join=True)
    no_auto_run = fields.Boolean('No run')
    # could be a default value, but possible to change it to allow duplicate accros branches

    description = fields.Char('Description', help='Informative description')
    md_description = fields.Char(compute='_compute_md_description', string='MD Parsed Description', help='Informative description markdown parsed')
    display_name = fields.Char(compute='_compute_display_name')

    # Related fields for convenience
    version_id = fields.Many2one('runbot.version', related='params_id.version_id', store=True, index=True)
    config_id = fields.Many2one('runbot.build.config', related='params_id.config_id', store=True, index=True)
    trigger_id = fields.Many2one('runbot.trigger', related='params_id.trigger_id', store=True, index=True)
    create_batch_id = fields.Many2one('runbot.batch', related='params_id.create_batch_id', store=True, index=True)

    # state machine
    global_state = fields.Selection(make_selection(state_order), string='Status', compute='_compute_global_state', store=True, recursive=True)
    local_state = fields.Selection(make_selection(state_order), string='Build Status', default='pending', required=True, index=True)
    global_result = fields.Selection(make_selection(result_order), string='Result', compute='_compute_global_result', store=True, recursive=True)
    local_result = fields.Selection(make_selection(result_order), string='Build Result', default='ok')

    requested_action = fields.Selection([('wake_up', 'To wake up'), ('deathrow', 'To kill')], string='Action requested', index=True)
    # web infos
    host = fields.Char('Host name')
    host_id = fields.Many2one('runbot.host', string="Host", compute='_compute_host_id')
    keep_host = fields.Boolean('Keep host on rebuild and for children')

    port = fields.Integer('Port')
    dest = fields.Char(compute='_compute_dest', type='char', string='Dest', readonly=True, store=True)
    domain = fields.Char(compute='_compute_domain', type='char', string='URL')
    # logs and stats
    log_ids = fields.One2many('ir.logging', 'build_id', string='Logs')
    error_log_ids = fields.One2many('ir.logging', 'build_id', domain=[('level', 'in', ['WARNING', 'ERROR', 'CRITICAL'])], string='Error Logs')
    stat_ids = fields.One2many('runbot.build.stat', 'build_id', string='Statistics values')
    log_list = fields.Char('Comma separted list of step_ids names with logs')

    active_step = fields.Many2one('runbot.build.config.step', 'Active step')
    job = fields.Char('Active step display name', compute='_compute_job')
    job_start = fields.Datetime('Job start')
    job_end = fields.Datetime('Job end')
    build_start = fields.Datetime('Build start')
    build_end = fields.Datetime('Build end')
    docker_start = fields.Datetime('Docker start')
    job_time = fields.Integer(compute='_compute_job_time', string='Job time')
    build_time = fields.Integer(compute='_compute_build_time', string='Build time')
    wait_time = fields.Integer(compute='_compute_wait_time', string='Wait time')
    load_time = fields.Integer(compute='_compute_load_time', string='Load time')
    last_update = fields.Datetime(compute='_compute_last_update', string='Last update')

    gc_date = fields.Datetime('Local cleanup date', compute='_compute_gc_date')
    gc_delay = fields.Integer('Cleanup Delay', help='Used to compute gc_date')

    build_age = fields.Integer(compute='_compute_build_age', string='Build age')

    coverage = fields.Boolean('Code coverage was computed for this build')
    coverage_result = fields.Float('Coverage result', digits=(5, 2))
    build_type = fields.Selection([('scheduled', 'This build was automatically scheduled'),
                                   ('rebuild', 'This build is a rebuild'),
                                   ('normal', 'normal build'),
                                   ('indirect', 'Automatic rebuild'), # TODO cleanup remove
                                   ('priority', 'Priority'),
                                   ],
                                  default='normal',
                                  string='Build type')

    parent_id = fields.Many2one('runbot.build', 'Parent Build', index=True)
    parent_path = fields.Char('Parent path', index=True, unaccent=False)
    top_parent =  fields.Many2one('runbot.build', compute='_compute_top_parent')
    ancestors =  fields.Many2many('runbot.build', compute='_compute_ancestors')
    # should we add a has children stored boolean?
    children_ids = fields.One2many('runbot.build', 'parent_id')

    # config of top_build is inherithed from params, but subbuild will have different configs

    orphan_result = fields.Boolean('No effect on the parent result', default=False)

    build_url = fields.Char('Build url', compute='_compute_build_url', store=False)
    build_error_link_ids = fields.One2many('runbot.build.error.link', 'build_id')
    build_error_ids = fields.Many2many('runbot.build.error', compute='_compute_build_error_ids', string='Errors')
    keep_running = fields.Boolean('Keep running', help='Keep running', index=True)
    log_counter = fields.Integer('Log Lines counter', default=100)

    slot_ids = fields.One2many('runbot.batch.slot', 'build_id')
    killable = fields.Boolean('Killable')

    database_ids = fields.One2many('runbot.database', 'build_id')
    commit_export_ids = fields.One2many('runbot.commit.export', 'build_id')

    static_run = fields.Char('Static run URL')

    access_token = fields.Char('Token', default=lambda self: uuid.uuid4().hex)

    @api.depends('description', 'params_id.config_id')
    def _compute_display_name(self):
        for build in self:
            build.display_name = build.description or build.config_id.name

    @api.depends('host')
    def _compute_host_id(self):
        get_host = self.env['runbot.host']._get_host
        for record in self:
            record.host_id = get_host(record.host)

    @api.depends('children_ids.global_state', 'local_state')
    def _compute_global_state(self):
        for record in self:
            waiting_score = record._get_state_score('waiting')
            children_ids = [child for child in record.children_ids if not child.orphan_result]
            if record._get_state_score(record.local_state) > waiting_score and children_ids:  # if finish, check children
                children_state = record._get_youngest_state([child.global_state for child in children_ids])
                if record._get_state_score(children_state) > waiting_score:
                    record.global_state = record.local_state
                else:
                    record.global_state = 'waiting'
            else:
                record.global_state = record.local_state

    @api.depends('gc_delay', 'job_end')
    def _compute_gc_date(self):
        icp = self.env['ir.config_parameter'].sudo()
        max_days_main = int(icp.get_param('runbot.db_gc_days', default=30))
        max_days_child = int(icp.get_param('runbot.db_gc_days_child', default=15))
        for build in self:
            ref_date = fields.Datetime.from_string(build.job_end or build.create_date or fields.Datetime.now())
            max_days = max_days_main if not build.parent_id else max_days_child
            max_days += int(build.gc_delay if build.gc_delay else 0)
            build.gc_date = ref_date + datetime.timedelta(days=(max_days))

    @api.depends('description')
    def _compute_md_description(self):
        for build in self:
            build.md_description = pseudo_markdown(build.description)

    def _compute_top_parent(self):
        for build in self:
            build.top_parent = self.browse(int(build.parent_path.split('/')[0]))

    def _compute_ancestors(self):
        for build in self:
            build.ancestors = self.browse([int(b) for b in build.parent_path.split('/') if b])

    def _get_youngest_state(self, states):
        index = min([self._get_state_score(state) for state in states])
        return state_order[index]

    def _get_state_score(self, result):
        return state_order.index(result)

    @api.depends('children_ids.global_result', 'local_result', 'children_ids.orphan_result')
    def _compute_global_result(self):
        for record in self:
            if record.local_result and record._get_result_score(record.local_result) >= record._get_result_score('ko'):
                record.global_result = record.local_result
            else:
                children_ids = [child for child in record.children_ids if not child.orphan_result]
                if children_ids:
                    children_result = record._get_worst_result([child.global_result for child in children_ids], max_res='ko')
                    if record.local_result:
                        record.global_result = record._get_worst_result([record.local_result, children_result])
                    else:
                        record.global_result = children_result
                else:
                    record.global_result = record.local_result

    @api.depends('build_error_link_ids')
    def _compute_build_error_ids(self):
        for record in self:
            record.build_error_ids = record.build_error_link_ids.error_content_id.error_id

    def _get_worst_result(self, results, max_res=False):
        results = [result for result in results if result]  # filter Falsy values
        index = max([self._get_result_score(result) for result in results]) if results else 0
        if max_res:
            return result_order[min([index, self._get_result_score(max_res)])]
        return result_order[index]

    def _get_result_score(self, result):
        return result_order.index(result)

    def _get_run_token(self):
        token = self.access_token or self.params_id.fingerprint
        token_info = hex(hash(token or '' + str(self.env.user.id)))[-4:]
        return (token[:8], token_info[:4])

    def _get_run_url(self, db_suffix=None):
        if db_suffix is None:
            db_suffix = self.mapped('database_ids')[0].db_suffix
        if self.env.user._is_internal():
            token, token_info = self._get_run_token()
            db_suffix = f'{db_suffix}-{token}-{token_info}'
        use_ssl = self.env['ir.config_parameter'].sudo().get_param('runbot.use_ssl', default=True)
        scheme = 'https' if use_ssl else 'http'
        return f'{scheme}://{self.dest}-{db_suffix}.{self.host}'

    @api.depends('active_step')
    def _compute_job(self):
        for build in self:
            build.job = build.active_step.name

    def copy_data(self, default=None):
        values = super().copy_data(default)[0] or {}
        default = dict(default or [])
        values = {key: value for key, value in values.items() if (key in COPY_WHITELIST or key in default)}
        values.update({
            'host': 'PAUSED',  # hack to keep the build in pending waiting for a manual update. Todo: add a paused flag instead
            'local_state': 'pending',
        })
        return [values]

    def write(self, values):
        # some validation to ensure db consistency
        if 'local_state' in values:
            if values['local_state'] == 'done':
                self.filtered(lambda b: b.local_state != 'done').commit_export_ids.unlink()

        local_result = values.get('local_result')
        for build in self:
            if local_result and local_result != self._get_worst_result([build.local_result, local_result]):  # dont write ok on a warn/error build
                if len(self) == 1:
                    values.pop('local_result')
                else:
                    raise ValidationError('Local result cannot be set to a less critical level')
        init_global_results = self.mapped('global_result')
        init_global_states = self.mapped('global_state')
        init_local_states = self.mapped('local_state')

        res = super(BuildResult, self).write(values)
        for init_global_result, build in zip(init_global_results, self):
            if init_global_result != build.global_result:
                build._github_status()

        for init_local_state, build in zip(init_local_states, self):
            if init_local_state not in ('done', 'running') and build.local_state in ('done', 'running'):
                build.build_end = now()

        for init_global_state, build in zip(init_global_states, self):
            if init_global_state not in ('done', 'running') and build.global_state in ('done', 'running'):
                build._github_status()

        return res

    def _add_child(self, param_values, orphan=False, description=False, additionnal_commit_links=False):

        if len(self.parent_path.split('/')) > 8:
            self._log('_run_create_build', 'This is too deep, skipping create')
            return self

        if additionnal_commit_links:
            commit_link_ids = self.params_id.commit_link_ids
            commit_link_ids |= additionnal_commit_links
            param_values['commit_link_ids'] = commit_link_ids

        return self.create({
            'params_id': self.params_id.copy(param_values).id,
            'parent_id': self.id,
            'build_type': self.build_type,
            'description': description,
            'orphan_result': orphan,
            'keep_host': self.keep_host,
            'host': self.host if self.keep_host else False,
        })

    def _result_multi(self):
        if all(build.global_result == 'ok' or not build.global_result for build in self):
            return 'ok'
        if any(build.global_result in ('skipped', 'killed', 'manually_killed') for build in self):
            return 'killed'
        if any(build.global_result == 'ko' for build in self):
            return 'ko'
        if any(build.global_result == 'warning' for build in self):
            return 'warning'
        return 'ko'  # ?

    @api.depends('params_id.version_id.name')
    def _compute_dest(self):
        for build in self:
            if build.id:
                nickname = build.params_id.version_id.name
                nickname = re.sub(r'"|\'|~|\:', '', nickname)
                nickname = re.sub(r'_|/|\.', '-', nickname)
                build.dest = ("%05d-%s" % (build.id or 0, nickname[:32])).lower()

    @api.depends('port', 'dest', 'host')
    def _compute_domain(self):
        for build in self:
            build.domain = "%s.%s" % (build.dest, build.host)

    @api.depends_context('batch')
    def _compute_build_url(self):
        batch = self.env.context.get('batch')
        for build in self:
            if batch:
                build.build_url = "/runbot/batch/%s/build/%s" % (batch.id, build.id)
            else:
                build.build_url = "/runbot/build/%s" % build.id

    @api.depends('job_start', 'job_end')
    def _compute_job_time(self):
        """Return the time taken by the tests"""
        for build in self:
            if build.job_end and build.job_start:
                build.job_time = int(dt2time(build.job_end) - dt2time(build.job_start))
            elif build.job_start:
                build.job_time = int(time.time() - dt2time(build.job_start))
            else:
                build.job_time = 0

    @api.depends('build_start', 'build_end', 'global_state')
    def _compute_build_time(self):
        for build in self:
            if build.build_end and build.build_start:
                build.build_time = int(dt2time(build.build_end) - dt2time(build.build_start))
            elif build.build_start:
                build.build_time = int(time.time() - dt2time(build.build_start))
            else:
                build.build_time = 0

    #@api.depends('create_date', 'last_update')
    def _compute_wait_time(self):
        for build in self:
            build.wait_time = dt2time(build.last_update) - dt2time(build.create_date)

    #@api.depends('build_end', 'children_ids.last_update')
    def _compute_last_update(self):
        for build in self:
            if not build.build_end:
                build.last_update = datetime.datetime.now()
            else:
                build.last_update = max([child.last_update for child in build.children_ids] + [build.build_end])

    #@api.depends('build_time', 'children_ids.load_time')
    def _compute_load_time(self):
        for build in self:
            build.load_time = sum([build.build_time] + [child.load_time for child in build.children_ids])

    @api.depends('job_start')
    def _compute_build_age(self):
        """Return the time between job start and now"""
        for build in self:
            if build.job_start:
                build.build_age = int(time.time() - dt2time(build.build_start))
            else:
                build.build_age = 0

    def _rebuild(self, message=None):
        """Force a rebuild and return a recordset of builds"""
        self.ensure_one()
        # TODO don't rebuild if there is a more recent build for this params?
        values = {
            'params_id': self.params_id.id,
            'build_type': 'rebuild',
        }
        if self.keep_host:
            values['host'] = self.host
            values['keep_host'] = True
        if self.parent_id:
            values.update({
                'parent_id': self.parent_id.id,
                'description': self.description,
            })
            self.orphan_result = True

        new_build = self.create(values)
        if self.parent_id:
            new_build._github_status()
        user = self.env.user
        new_build._log('rebuild', 'Rebuild initiated by %s%s' % (user.name, (' :%s' % message) if message else ''))

        if self.local_state != 'done':
            self._ask_kill('Killed by rebuild requested by %s (%s) (new build:%s)' % (user.name, user.id, new_build.id))

        if not self.parent_id:
            slots = self.env['runbot.batch.slot'].search([('build_id', '=', self.id)])
            for slot in slots:
                slot.copy({
                    'build_id': new_build.id,
                    'link_type': 'rebuild',
                })
                slot.active = False
        return new_build

    def _skip(self, reason=None):
        """Mark builds ids as skipped"""
        if reason:
            self._logger('skip %s', reason)
        self.write({'local_state': 'done', 'local_result': 'skipped'})

    def _build_from_dest(self, dest):
        if dest_reg.match(dest):
            return self.browse(int(dest.split('-')[0]))
        return self.browse()

    def _filter_to_clean(self, dest_list, label):
        dest_by_builds_ids = defaultdict(list)
        ignored = set()
        icp = self.env['ir.config_parameter']
        hide_in_logs = icp.get_param('runbot.runbot_db_template', default='template0')

        for dest in dest_list:
            build = self._build_from_dest(dest)
            if build:
                dest_by_builds_ids[build.id].append(dest)
            elif dest != hide_in_logs:
                ignored.add(dest)
        if ignored:
            _logger.info('%s (%s) not deleted because not dest format', label, list(ignored))
        builds = self.browse(dest_by_builds_ids)
        existing = builds.exists()
        remaining = (builds - existing)
        if remaining:
            dest_list = [dest for sublist in [dest_by_builds_ids[rem_id] for rem_id in remaining.ids] for dest in sublist]
            _logger.info('(%s) (%s) not deleted because no corresponding build found', label, " ".join(dest_list))
        for build in existing:
            if build.gc_date < fields.datetime.now():
                if build.local_state == 'done':
                    for db in dest_by_builds_ids[build.id]:
                        yield db
                elif build.local_state != 'running':
                    _logger.warning('db (%s) not deleted because state is not done', " ".join(dest_by_builds_ids[build.id]))

    def _local_cleanup(self, force=False, full=False):
        """
        Remove datadir and drop databases of build older than db_gc_days or db_gc_days_child.
        If force is set to True, does the same cleaning based on recordset without checking build age.
        """
        _logger.info('Local cleaning')
        _filter = self._filter_to_clean
        additionnal_conditions = []

        if force is True:
            def filter_ids(dest_list, label):
                for dest in dest_list:
                    build = self._build_from_dest(dest)
                    if build and build in self:
                        yield dest
                    elif not build:
                        _logger.info('%s (%s) skipped because not dest format', label, dest)
            _filter = filter_ids
            for _id in self.exists().ids:
                additionnal_conditions.append("datname like '%s-%%'" % _id)

        log_db = self.env['ir.config_parameter'].get_param('runbot.logdb_name')
        existing_db = [db for db in list_local_dbs(additionnal_conditions=additionnal_conditions) if db != log_db]

        for db in _filter(dest_list=existing_db, label='db'):
            self._logger('Removing database')
            self._local_pg_dropdb(db)

        builds_dir = Path(self.env['runbot.runbot']._root()) / 'build'
        if force:
            dest_list = [build.dest for build in self]
        else:
            dest_list = (p.name for p in builds_dir.iterdir())

        icp = self.env['ir.config_parameter']
        full_gc_days = int(icp.get_param('runbot.full_gc_days', default=365))
        full_gc_secondes = full_gc_days * 24 * 60 * 60
        now = time.time()

        candidate_for_partial_gc = []
        for dest in dest_list:
            build_dir = Path(builds_dir) / dest
            gcstamp = build_dir / '.gcstamp'
            try:
                if (force and full) or gcstamp.stat().st_ctime + full_gc_secondes < now:
                    _logger.info('Removing build dir "%s"', dest)
                    shutil.rmtree(build_dir, ignore_errors=True)
                    continue
            except(FileNotFoundError):
                candidate_for_partial_gc.append(dest)
        if candidate_for_partial_gc:
            for dest in _filter(candidate_for_partial_gc, label='workspace'):
                build_dir = Path(builds_dir) / dest
                gcstamp = build_dir / '.gcstamp'
                for bdir_file in build_dir.iterdir():
                    if bdir_file.is_dir() and bdir_file.name not in ('logs', 'tests'):
                        shutil.rmtree(bdir_file)
                    elif bdir_file.name == 'logs':
                        for log_file_path in bdir_file.iterdir():
                            if log_file_path.is_dir():
                                shutil.rmtree(log_file_path)
                            elif log_file_path.name in ('run.txt', 'wake_up.txt') or not log_file_path.name.endswith('.txt'):
                                log_file_path.unlink()
                    gcstamp.write_text(f'gc date: {datetime.datetime.now()}')

    def _find_port(self):
        # currently used port
        host_name = self.env['runbot.host']._get_current_name()
        ids = self.search([('local_state', 'not in', ['pending', 'done']), ('host', '=', host_name)])
        ports = set(i['port'] for i in ids.read(['port']))

        # starting port
        icp = self.env['ir.config_parameter']
        port = int(icp.get_param('runbot.runbot_starting_port', default=2000))

        # find next free port
        while port in ports:
            port += 3
        return port

    def _logger(self, *l):
        l = list(l)
        for build in self:
            l[0] = "%s %s" % (build.dest, l[0])
            _logger.info(*l)

    def _get_docker_name(self):
        self.ensure_one()
        return '%s_%s' % (self.dest, self.active_step.name)

    def _init_pendings(self):
        self.ensure_one()
        build = self
        build.port = self._find_port()
        build.job_start = now()
        build.build_start = now()
        build.job_end = False
        build._log('_schedule', 'Init build environment with config %s ' % build.params_id.config_id.name)
        try:
            os.makedirs(build._path('logs'), exist_ok=True)
        except Exception:
            _logger.exception('Failed initiating build %s', build.dest)
            build._log('_schedule', 'Failed initiating build')
            build._kill(result='ko')

    def _process_requested_actions(self):
        self.ensure_one()
        build = self
        if build.requested_action == 'deathrow':
            result = None
            if build.local_state != 'running' and build.global_result not in ('warn', 'ko'):
                result = 'manually_killed'
            build._kill(result=result)
            return

        if build.requested_action == 'wake_up':
            if build.local_state != 'done':
                build.requested_action = False
                build._log('wake_up', 'Impossible to wake-up, build is not done', log_type='markdown', level='SEPARATOR')
            elif not os.path.exists(build._path()):
                build.requested_action = False
                build._log('wake_up', 'Impossible to wake-up, **build dir does not exists anymore**', log_type='markdown', level='SEPARATOR')
            elif docker_state(build._get_docker_name(), build._path()) == 'RUNNING':
                build.write({'requested_action': False, 'local_state': 'running'})
                build._log('wake_up', 'Waking up failed, **docker is already running**', log_type='markdown', level='SEPARATOR')
            else:
                try:
                    log_path = build._path('logs', 'wake_up.txt')

                    port = self._find_port()
                    build.write({
                        'job_start': now(),
                        'job_end': False,
                        'active_step': False,
                        'requested_action': False,
                        'local_state': 'running',
                        'port': port,
                    })
                    build._log('wake_up', '**Waking up build**', log_type='markdown', level='SEPARATOR')
                    step_ids = build.params_id.config_id.step_ids
                    if step_ids and step_ids[-1]._step_state() == 'running':
                        run_step = step_ids[-1]
                    else:
                        run_step = self.env.ref('runbot.runbot_build_config_step_run')
                    run_step._run_step(build, force=True)()
                    # reload_nginx will be triggered by _run_run_odoo
                except Exception:
                    _logger.exception('Failed to wake up build %s', build.dest)
                    build._log('_schedule', 'Failed waking up build', level='ERROR')
                    build.write({'requested_action': False, 'local_state': 'done'})
            return

    def _schedule(self):
        """schedule the build"""
        icp = self.env['ir.config_parameter'].sudo()
        self.ensure_one()
        build = self
        if build.local_state not in ['testing', 'running', 'pending']:
            return False
        # check if current job is finished
        if build.local_state == 'pending':
            build._init_pendings()
        else:
            _docker_state = docker_state(build._get_docker_name(), build._path())
            if _docker_state == 'RUNNING':
                timeout = min(build.active_step.cpu_limit, int(icp.get_param('runbot.runbot_timeout', default=10000)))
                if build.local_state != 'running' and build.job_time > timeout:
                    build.active_step._make_stats(build)
                    build._log('_schedule', '%s time exceeded (%ss)' % (build.active_step.name if build.active_step else "?", build.job_time))
                    build._kill(result='killed')
                return False
            elif _docker_state in ('UNKNOWN', 'GHOST') and build.docker_start:
                docker_time = time.time() - dt2time(build.docker_start)
                if docker_time < 5:
                    return False
                elif docker_time < 60:
                    _logger.info('container "%s" seems too take a while to start :%s' % (build._get_docker_name(), build.job_time))
                    return False
                else:
                    build._log('_schedule', 'Docker with state %s not started after 60 seconds, skipping' % _docker_state, level='ERROR')
            if self.env['runbot.host']._fetch_local_logs(build_ids=build.ids):
                return True  # avoid to make results with remaining logs
            # No job running, make result and select next job

            build.job_end = now()
            build.docker_start = False
            # make result of previous job
            try:
                build.active_step._make_results(build)
            except Exception as e:
                if isinstance(e, RunbotException):
                    message = e.args[0][:300000]
                else:
                    message = 'An error occured while computing results of %s:\n %s' % (build.job, str(e).replace('\\n', '\n').replace("\\'", "'")[:10000])
                    _logger.exception(message)
                build._log('_make_results', message, level='ERROR')
                build.local_result = 'ko'

            # compute statistics before starting next job
            build.active_step._make_stats(build)
            build.active_step._log_end(build)

        step_ids = self.params_id.config_id.step_ids
        if not step_ids:  # no job to do, build is done
            self.active_step = False
            self.local_state = 'done'
            build._log('_schedule', 'No job in config, doing nothing')
            build.local_result = 'warn'
            return False

        if not self.active_step and self.local_state != 'pending':  # wakeup docker finished
            build.active_step = False
            build.local_state = 'done'
            return False

        if not self.active_step:
            next_index = 0
        else:
            if self.active_step not in step_ids:
                self._log('run', 'Config was modified and current step does not exists anymore, skipping.', level='ERROR')
                self.active_step = False
                self.local_state = 'done'
                self.local_result = 'ko'
                return False
            next_index = list(step_ids).index(self.active_step) + 1

        while True:
            if next_index >= len(step_ids):  # final job, build is done
                self.active_step = False
                self.local_state = 'done'
                return False
            new_step = step_ids[next_index]  # job to do, state is job_state (testing or running)
            if new_step.domain_filter and not self.filtered_domain(safe_eval(new_step.domain_filter)):
                self._log('run', '**Skipping** step ~~%s~~ from config **%s**', new_step.name, self.params_id.config_id.name, log_type='markdown', level='SEPARATOR')
                next_index += 1
                continue
            break

        if self.local_result == 'ko':
            if self.active_step and self.active_step.break_after_if_ko:
                self._log('break_on_ko', f'Build is in failure, stopping after {self.active_step.name}')
                self.local_state = 'done'
                self.active_step = False
                return
            if new_step.break_before_if_ko:
                self._log('break_on_ko', f'Build is in failure, stopping before {new_step.name}')
                self.local_state = 'done'
                self.active_step = False
                return

        build.active_step = new_step.id
        build.local_state = new_step._step_state()

        return build._run_job()

    def _run_job(self):
        self.ensure_one()
        build = self
        if build.local_state != 'done':
            build._logger('running %s', build.active_step.name)
            os.makedirs(build._path('logs'), exist_ok=True)
            os.makedirs(build._path('datadir'), exist_ok=True)
            try:
                return build.active_step._run(build)  # run should be on build?
            except TransactionRollbackError:
                raise
            except Exception as e:
                if isinstance(e, RunbotException):
                    message = e.args[0]
                else:
                    message = '%s failed running step %s:\n %s' % (build.dest, build.job, str(e).replace('\\n', '\n').replace("\\'", "'"))
                _logger.exception(message)
                build._log("run", message, level='ERROR')
                build._kill(result='ko')

    def _docker_run(self, step, cmd=None, ro_volumes=None, **kwargs):
        self.ensure_one()
        _ro_volumes = ro_volumes or {}
        ro_volumes = {}
        for dest, source in _ro_volumes.items():
            ro_volumes[f'/data/build/{dest}'] = source
        if 'image_tag' not in kwargs:
            kwargs.update({'image_tag': self.params_id.dockerfile_id.image_tag})
        self._log('Preparing', 'Using Dockerfile Tag [%s](/runbot/dockerfile/tag/%s)', kwargs['image_tag'], kwargs['image_tag'], log_type='markdown')
        icp = self.env['ir.config_parameter']
        docker_registry_host = self.env['runbot.host'].browse(int(icp.get_param('runbot.docker_registry_host_id', default=0)))
        if docker_registry_host and self.host_id.use_remote_docker_registry:
            result = docker_pull(f"dockerhub.{docker_registry_host.name}/{kwargs['image_tag']}")
            if result['success']:
                result['image'].tag(kwargs['image_tag'])
            if result.get('log_progress'):
                self._log('Docker Run', f'Docker image was pulled {"" if result["success"] else "with errors"}')

        containers_memory_limit = self.env['ir.config_parameter'].sudo().get_param('runbot.runbot_containers_memory', 0)
        if containers_memory_limit and 'memory' not in kwargs:
            kwargs['memory'] = int(float(containers_memory_limit) * 1024 ** 3)

        self.docker_start = now()
        if self.job_start:
            start_step_time = int(dt2time(self.docker_start) - dt2time(self.job_start))
            if start_step_time > 60:
                _logger.info('Step took %s seconds before starting docker', start_step_time)

        starting_config = self.env['ir.config_parameter'].sudo().get_param('runbot.runbot_default_odoorc')
        if isinstance(cmd, Command):
            rc_content = cmd.get_config(starting_config=starting_config)
        else:
            rc_content = starting_config
        self._write_file('.odoorc', rc_content)
        ro_volumes[f'/home/{USERNAME}/.odoorc'] = self._path('.odoorc')
        kwargs.pop('build_dir', False)
        kwargs.pop('log_path', False)
        kwargs.pop('container_name', False)
        log_path = self._path('logs', '%s.txt' % step.name)
        build_dir = self._path()
        container_name = self._get_docker_name()
        self.env.flush_all()
        def start_docker():
            docker_run(
                cmd=cmd,
                container_name=container_name,
                build_dir=build_dir,
                log_path=log_path,
                ro_volumes=ro_volumes, **kwargs)
        return start_docker

    def _path(self, *paths):
        """Return the repo build path"""
        self.ensure_one()
        return self.env['runbot.runbot']._path('build', self.dest, *paths)

    def _http_log_url(self):
        use_ssl = self.env['ir.config_parameter'].get_param('runbot.use_ssl', default=True)
        return '%s://%s/runbot/static/build/%s/logs/' % ('https' if use_ssl else 'http', self.host, self.dest)

    def _server(self, *path):
        """Return the absolute path to the direcory containing the server file, adding optional *path"""
        self.ensure_one()
        commit = self._get_server_commit()
        return commit._source_path('odoo', *path)

    def _docker_source_folder(self, commit):
        return sanitize(commit.repo_id.name)

    def _checkout(self):
        self.ensure_one()  # will raise exception if hash not found, we don't want to fail for all build.
        # checkout branch
        start = time.time()
        exports = {}
        for commit in self.env.context.get('defined_commit_ids') or self.params_id.commit_ids:
            build_export_path = self._docker_source_folder(commit)
            if build_export_path in exports:
                self._log('_checkout', 'Multiple repo have same export path in build, some source may be missing for %s' % build_export_path, level='ERROR')
                self._kill(result='ko')
            exports[build_export_path] = commit._export(self)

        checkout_time = time.time() - start
        if checkout_time > 60:
            self._log('checkout', 'Checkout took %s seconds' % int(checkout_time))

        return exports

    def _get_available_modules(self):
        all_modules = dict()
        available_modules = defaultdict(list)
        # repo_modules = []
        for commit in self.env.context.get('defined_commit_ids') or self.params_id.commit_ids:
            for (addons_path, module, manifest_file_name) in commit._get_available_modules():
                if module in all_modules:
                    self._log(
                        'Building environment',
                        '%s is a duplicated modules (found in "%s", already defined in %s)' % (
                            module,
                            commit._source_path(addons_path, module, manifest_file_name),
                            all_modules[module]._source_path(addons_path, module, manifest_file_name)),
                        level='WARNING'
                    )
                else:
                    available_modules[commit.repo_id].append(module)
                    all_modules[module] = commit
        # return repo_modules, available_modules
        return available_modules

    def _get_modules_to_test(self, modules_patterns=''):
        self.ensure_one()
        trigger = self.params_id.trigger_id
        modules = self._get_available_modules()
        params_patterns = (self.params_id.modules or '').split(',')
        modules_patterns = (modules_patterns or '').split(',')
        return trigger._filter_modules_to_test(modules, params_patterns + modules_patterns)  # we may switch params_patterns and modules_patterns order

    def _local_pg_dropdb(self, dbname):
        msg = ''
        try:
            with local_pgadmin_cursor() as local_cr:
                query = 'SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname=%s'
                local_cr.execute(query, [dbname])
                local_cr.execute('DROP DATABASE IF EXISTS "%s"' % dbname)
        except Exception as e:
            msg = f"Failed to drop local logs database : {dbname} with exception: {e}"
            _logger.exception(msg)
            host_name = self.env['runbot.host']._get_current_name()
            self.env['runbot.runbot']._warning(f'Host {host_name}: {msg}')

    def _local_pg_createdb(self, dbname):
        icp = self.env['ir.config_parameter']
        db_template = icp.get_param('runbot.runbot_db_template', default='template0')
        self._local_pg_dropdb(dbname)
        _logger.info("createdb %s", dbname)
        with local_pgadmin_cursor() as local_cr:
            local_cr.execute(sql.SQL("""CREATE DATABASE {} TEMPLATE %s LC_COLLATE 'C' ENCODING 'unicode'""").format(sql.Identifier(dbname)), (db_template,))
        self.env['runbot.database'].create({'name': dbname, 'build_id': self.id})

    def _log(self, func, message, *args, level='INFO', log_type='runbot', path='runbot'):
        def truncate(message, maxlenght=300000):
            if len(message) > maxlenght:
                return message[:maxlenght] + '[Truncate, message too long]'
            return message

        if log_type == 'markdown':
            args = tuple([markdown_escape(truncate(str(arg), maxlenght=200000)) for arg in args])

        if args:
            try:
                message = message % args
            except TypeError:
                _logger.exception(f'Error while formating `{message}` with `{args}`')
                message = ' ' .join([message, *map(str, args)])

        message = truncate(message)

        self.ensure_one()
        #_logger.info("Build %s %s %s", self.id, func, message)
        return self.env['ir.logging'].create({
            'build_id': self.id,
            'level': level,
            'type': log_type,
            'name': 'odoo.runbot',
            'message': message,
            'path': path,
            'func': func,
            'line': '0',
        })

    def _kill(self, result=None):
        host_name = self.env['runbot.host']._get_current_name()
        self.ensure_one()
        build = self
        if build.host != host_name:
            return
        build._log('kill', 'Kill build %s' % build.dest)
        docker_stop(build._get_docker_name(), build._path())
        v = {'local_state': 'done', 'requested_action': False, 'active_step': False, 'job_end': now()}
        if not build.build_end:
            v['build_end'] = now()
        if result:
            v['local_result'] = result
        build.write(v)

    def _ask_kill(self, lock=True, message=None):
        # if build remains in same bundle, it's ok like that
        # if build can be cross bundle, need to check number of ref to build
        if lock:
            self.env.cr.execute("""SELECT id FROM runbot_build WHERE parent_path like %s FOR UPDATE""", ['%s%%' % self.parent_path])
        self.ensure_one()
        user = self.env.user
        uid = user.id
        build = self
        message = message or 'Killing build %s, requested by %s (user #%s)' % (build.dest, user.name, uid)
        build._log('_ask_kill', message)
        if build.local_state == 'pending':
            build._skip()
        elif build.local_state in ['testing', 'running']:
            build.requested_action = 'deathrow'
        for child in build.children_ids:
            child._ask_kill(lock=False)

    def _wake_up(self):
        user = self.env.user
        self._log('wake_up', f'Wake up initiated by {user.name}')
        if self.local_state != 'done':
            self._log('wake_up', 'Impossibe to wake up, state is not done')
        elif self.parent_id.database_ids and not user.has_group('runbot.group_runbot_advanced_user'):
            self._log('wake_up', 'Waking up child builds is for advanced users only')
        else:
            self.requested_action = 'wake_up'

    def _get_server_commit(self):
        """
        returns a commit of the first repo containing server files found in commits or in build commits
        the commits param is not used in code base but could be usefull for jobs and crons
        """
        for commit in (self.env.context.get('defined_commit_ids') or self.params_id.commit_ids):
            if commit.repo_id.server_files:
                return commit
        raise ValidationError('No repo found with defined server_files')

    def _get_addons_path(self):
        for commit in (self.env.context.get('defined_commit_ids') or self.params_id.commit_ids):
            if not commit.repo_id.manifest_files:
                continue  # skip repo without addons
            repo_folder = self._docker_source_folder(commit)
            for addons_path in (commit.repo_id.addons_paths or '').split(','):
                if os.path.isdir(commit._source_path(addons_path)):
                    yield os.sep.join([repo_folder, addons_path]).strip(os.sep)

    def _get_upgrade_path(self):
        for commit in (self.env.context.get('defined_commit_ids') or self.params_id.commit_ids):
            if not commit.repo_id.upgrade_paths:
                continue  # skip repo without addons
            repo_folder = self._docker_source_folder(commit)
            for upgrade_path in commit.repo_id.upgrade_paths.split(','):
                if os.path.isdir(commit._source_path(upgrade_path)):
                    yield os.sep.join([repo_folder, upgrade_path]).strip(os.sep)

    def _get_server_info(self, commit=None):
        commit = commit or self._get_server_commit()
        for server_file in commit.repo_id.server_files.split(','):
            if os.path.isfile(commit._source_path(server_file)):
                return (commit, server_file)
        _logger.error('None of %s found in commit, actual commit content:\n %s' % (commit.repo_id.server_files, os.listdir(commit._source_path())))
        raise RunbotException('No server found in %s' % commit.dname)

    def _cmd(self, python_params=None, py_version=None, local_only=True, sub_command=None, enable_log_db=True):
        """Return a list describing the command to start the build
        """
        self.ensure_one()
        build = self
        python_params = python_params or []
        py_version = py_version if py_version is not None else build._get_py_version()
        pres = []
        if not self.params_id.skip_requirements and not self.params_id.config_data.get('skip_requirements'):
            for commit_id in self.env.context.get('defined_commit_ids') or self.params_id.commit_ids.sorted(lambda c: (c.repo_id.sequence, c.repo_id.id)):
                if os.path.isfile(commit_id._source_path('requirements.txt')):
                    repo_dir = self._docker_source_folder(commit_id)
                    requirement_path = os.sep.join([repo_dir, 'requirements.txt'])
                    pres.append([f'python{py_version}', '-m', 'pip', 'install', '--user', '--progress-bar', 'off', '-r', f'{requirement_path}'])

        addons_paths = self._get_addons_path()
        (server_commit, server_file) = self._get_server_info()
        server_dir = self._docker_source_folder(server_commit)

        # commandline
        cmd = ['python%s' % py_version] + python_params + [os.sep.join([server_dir, server_file])]
        if sub_command:
            cmd += [sub_command]

        if not self.params_id.extra_params or '--addons-path' not in self.params_id.extra_params:
            cmd += ['--addons-path', ",".join(addons_paths)]

        # options
        config_path = build._server("tools/config.py")
        if grep(config_path, "no-xmlrpcs"):  # move that to configs ?
            cmd.append("--no-xmlrpcs")
        if grep(config_path, "no-netrpc"):
            cmd.append("--no-netrpc")

        pres += self.params_id.config_data.get('pres', [])
        posts = self.params_id.config_data.get('posts', [])
        finals = self.params_id.config_data.get('finals', [])
        config_tuples = self.params_id.config_data.get('config_tuples', [])

        command = Command(pres, cmd, posts, finals=finals, config_tuples=config_tuples, cmd_checker=build) 

        # use the username of the runbot host to connect to the databases
        command.add_config_tuple('db_user', '%s' % pwd.getpwuid(USERUID).pw_name)

        if local_only:
            if grep(config_path, "--http-interface"):
                command.add_config_tuple("http_interface", "127.0.0.1")
            elif grep(config_path, "--xmlrpc-interface"):
                command.add_config_tuple("xmlrpc_interface", "127.0.0.1")

        if enable_log_db:
            log_db = self.env['ir.config_parameter'].get_param('runbot.logdb_name')
            if grep(config_path, "log-db"):
                command.add_config_tuple("log_db", log_db)
                if grep(config_path, 'log-db-level'):
                    command.add_config_tuple("log_db_level", '25')

        if grep(config_path, "data-dir"):
            datadir = build._path('datadir')
            if not os.path.exists(datadir):
                os.mkdir(datadir)
            command.add_config_tuple("data_dir", '/data/build/datadir')

        return command

    def _cmd_check(self, cmd):
        """
        Check the cmd right before creating the build command line executed in
        a Docker container. If a database creation is found in the cmd, a
        'runbot.database' is created.
        This method is intended to be called from cmd itself
        """
        if '-d' in cmd:
            dbname = cmd[cmd.index('-d') + 1]
            self.env['runbot.database'].create({
                'name': dbname,
                'build_id': self.id
            })

    def _get_py_version(self):
        """return the python name to use from build batch"""
        (server_commit, server_file) = self._get_server_info()
        server_path = server_commit._source_path(server_file)
        with file_open(server_path, 'r') as f:
            if f.readline().strip().endswith('python3'):
                return '3'
        return ''

    def _parse_logs(self):
        """ Parse build logs to classify errors """
        # only parse logs from builds in error and not already scanned
        builds_to_scan = self.filtered(lambda b: b.local_result in ('ko', 'killed', 'warn') and not b.build_error_link_ids)
        ir_logs = builds_to_scan.log_ids.filtered(lambda l: l.level in ('ERROR', 'WARNING', 'CRITICAL'))
        return self.env['runbot.build.error']._parse_logs(ir_logs)

    def _is_file(self, file, mode='r'):
        file_path = self._path(file)
        return os.path.exists(file_path)

    def _read_file(self, file, mode='r'):
        file_path = self._path(file)
        try:
            with file_open(file_path, mode) as f:
                return f.read()
        except Exception as e:
            self._log('readfile', 'exception: %s' % e)
            return False

    def _write_file(self, file, data, mode='w'):
        _file_path = self._path(file)
        file_dir = os.path.dirname(_file_path)
        os.makedirs(file_dir, exist_ok=True)
        file_path(os.path.dirname(_file_path))
        try:
            with open(_file_path, mode) as f:
                f.write(data)
        except Exception as e:
            self._log('write_file', 'exception: %s' % e)
            return False

    def _get_color_class(self):

        if self.global_result == 'ko':
            return 'danger'
        if self.global_result == 'warn':
            return 'warning'

        if self.global_state == 'pending':
            return 'default'
        if self.global_state in ('testing', 'waiting'):
            return 'info'

        if self.global_result == 'ok':
            return 'success'

        if self.global_result in ('skipped', 'killed', 'manually_killed'):
            return 'secondary'
        return 'default'

    def _github_status(self):
        """Notify github of failed/successful builds"""
        for build in self:
            # TODO maybe avoid to send status if build is killable (another new build exist and will send the status)
            if build.parent_id:
                if build.orphan_result:
                    _logger.info('Skipping result for orphan build %s', self.id)
                else:
                    build.parent_id._github_status()
            else:
                trigger = self.params_id.trigger_id
                if not trigger.ci_context:
                    continue

                desc = trigger.ci_description or " (runtime %ss)" % (build.job_time,)
                if build.params_id.used_custom_trigger:
                    state = 'error'
                    desc = "This build used custom config. Remove custom trigger to restore default ci"
                elif build.global_result in ('ko', 'warn'):
                    state = 'failure'
                elif build.global_state in ('pending', 'testing'):
                    state = 'pending'
                elif build.global_state in ('running', 'done'):
                    state = 'error'
                    if build.global_result == 'ok':
                        state = 'success'
                else:
                    _logger.info("skipping github status for build %s ", build.id)
                    continue

                target_url = trigger.ci_url or "%s/runbot/build/%s" % (self.get_base_url(), build.id)
                for build_commit in self.params_id.commit_link_ids:
                    commit = build_commit.commit_id
                    if 'base_' not in build_commit.match_type and commit.repo_id in trigger.repo_ids:
                        commit._github_status(build, trigger.ci_context, state, target_url, desc)

    def _parse_config(self):
        return set(findall(self._server("tools/config.py"), r'--[\w-]+', ))
