# -*- coding: utf-8 -*-
'''
	LF-Portal
	~~~~~~~~~

	Defined colors for some facilities

	:license: GPL, see LICENSE for more details.
'''

# Set default encoding to UTF-8
import sys
reload(sys)
sys.setdefaultencoding('utf8')


def seriescolor(id, contributor, config):

        if 'Theologische Fakul' in contributor: return '000000'
        if 'Juristische und Wirtschaftswissenschaftliche Fakul' in contributor: return 'aa263c'
        if 'Medizinische Fakul' in contributor: return 'bb2b16'
        if 'Philosophische Fakul' in contributor: return '993c8c'
        if 't III' in contributor: return '368429' # Naturwiss. Fak. III
        if 'Naturwissenschaftliche Fakul' in contributor: return '2d7aab' # Naturwiss. Fak. I und II
        if 'Ingenieurwissenschaften' in contributor: return '627b86'
        if 'LLZ' in contributor: return '2085A8'

	return '330033'
