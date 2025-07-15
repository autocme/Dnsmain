#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# Import all models here
# Only import payment_transaction if payment module is available
try:
    from . import payment_transaction
except ImportError:
    # Payment module not available, skip payment transaction extension
    pass