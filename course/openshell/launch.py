"""Require concrete policy probes before launching the teaching agent."""
import runpy
# Probe raises on a missing allow, a missing denial, or an unexpected response.
runpy.run_module('course.openshell.probe', run_name='__main__')
runpy.run_module('course.agent.runtime', run_name='__main__')
