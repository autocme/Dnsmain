import builtins
import logging
import threading

import psycopg2

import odoo
from odoo import models

_logger = logging.getLogger(__name__)


class Base(models.AbstractModel):
    _inherit = 'base'

    def run_crons(self):
        builtins.current_date = self.env.context.get('current_date')
        builtins.forwardport_merged_before = self.env.context.get('forwardport_merged_before')
        self.env['ir.cron']._process_jobs(self.env.cr.dbname)
        del builtins.forwardport_merged_before
        return True


class IrCron(models.Model):
    _inherit = 'ir.cron'

    @classmethod
    def _process_jobs(cls, db_name):
        t = threading.current_thread()
        try:
            db = odoo.sql_db.db_connect(db_name)
            t.dbname = db_name
            with db.cursor() as cron_cr:
                # FIXME: override `_get_all_ready_jobs` to directly lock the cron?
                while job := next((
                    job
                    for j in cls._get_all_ready_jobs(cron_cr)
                    if (job := cls._acquire_one_job(cron_cr, (j['id'],)))
                ), None):
                    # take into account overridings of _process_job() on that database
                    registry = odoo.registry(db_name)
                    registry[cls._name]._process_job(db, cron_cr, job)
                    cron_cr.commit()

        except psycopg2.ProgrammingError as e:
            raise
        except Exception:
            _logger.warning('Exception in cron:', exc_info=True)
        finally:
            if hasattr(t, 'dbname'):
                del t.dbname
