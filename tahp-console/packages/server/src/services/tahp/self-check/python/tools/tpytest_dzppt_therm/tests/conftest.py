import sys

pytest_plugins = ['tpytest.testplugins.tpytest_conftest']

if getattr(sys, 'frozen', False):
    pytest_plugins.append('pytest_rerunfailures')
