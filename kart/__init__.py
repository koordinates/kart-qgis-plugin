# -*- coding: utf-8 -*-

# (c) 2016 Boundless, http://boundlessgeo.com
# This code is licensed under the GPL 2.0 license.

import os
import site

site.addsitedir(os.path.abspath(os.path.dirname(__file__) + '/extlibs'))


def classFactory(iface):
    from kart.plugin import KartPlugin
    return KartPlugin(iface)
