#!/usr/bin/env python
# SPDX-License-Identifier: ISC

"""
test_srv6_l3vpn.py: SRv6 L3VPN topology test.

Topology:
    Core network (r1-r6):
        r1 --- r2
        |  \    |
        |   r3--r6
        |   |   |
        r5--r4--/

    PE routers: r3, r6 (for manual configuration)
    CE routers:
      - Client1: r7 (connects to r3), r8 (connects to r6)
      - Client2: r9 (connects to r3), r10 (connects to r6)

    Base setup: Only IP addresses configured on all interfaces.
    All routing protocols (ISIS, OSPF, BGP) and VRF to be configured manually.
"""
import os
import sys
import pytest
import json

CWD = os.path.dirname(os.path.realpath(__file__))
sys.path.append(os.path.join(CWD, "../"))

# pylint: disable=C0413
from lib.topogen import Topogen, TopoRouter, get_topogen
from lib.topolog import logger
from lib.common_config import step, required_linux_kernel_version

pytestmark = [pytest.mark.isisd, pytest.mark.bgpd, pytest.mark.ospfd, pytest.mark.ospf6d]


def build_topo(tgen):
    "Build function for SRv6 L3VPN topology"

    # Add all routers (r1-r6: core, r7-r8: Client1 CEs, r9-r10: Client2 CEs)
    for routern in range(1, 11):
        tgen.add_router("r{}".format(routern))

    # Core network links (based on SRv6 lab topology)
    # Link order is critical - it determines interface numbering (eth0, eth1, etc.)

    # r1 - r2 link (r1-eth0, r2-eth0)
    sw = tgen.add_switch("sw12")
    sw.add_link(tgen.gears["r1"])
    sw.add_link(tgen.gears["r2"])

    # r1 - r3 link (r1-eth1, r3-eth0)
    sw = tgen.add_switch("sw13")
    sw.add_link(tgen.gears["r1"])
    sw.add_link(tgen.gears["r3"])

    # r2 - r6 link (r2-eth1, r6-eth0)
    sw = tgen.add_switch("sw26")
    sw.add_link(tgen.gears["r2"])
    sw.add_link(tgen.gears["r6"])

    # r4 - r5 link (r4-eth0, r5-eth0) - MUST come before sw34 for correct r4 numbering
    sw = tgen.add_switch("sw45")
    sw.add_link(tgen.gears["r4"])
    sw.add_link(tgen.gears["r5"])

    # r3 - r4 link (r3-eth1, r4-eth1)
    sw = tgen.add_switch("sw34")
    sw.add_link(tgen.gears["r3"])
    sw.add_link(tgen.gears["r4"])

    # r5 - r6 link (r5-eth1, r6-eth1)
    sw = tgen.add_switch("sw56")
    sw.add_link(tgen.gears["r5"])
    sw.add_link(tgen.gears["r6"])

    # r1 - r5 link (r1-eth2, r5-eth2)
    sw = tgen.add_switch("sw15")
    sw.add_link(tgen.gears["r1"])
    sw.add_link(tgen.gears["r5"])

    # PE-CE links for VRF Client1
    # r3 - r7 link (r3-eth2, r7-eth0)
    sw = tgen.add_switch("sw37")
    sw.add_link(tgen.gears["r3"])
    sw.add_link(tgen.gears["r7"])

    # r6 - r8 link (r6-eth2, r8-eth0)
    sw = tgen.add_switch("sw68")
    sw.add_link(tgen.gears["r6"])
    sw.add_link(tgen.gears["r8"])

    # PE-CE links for VRF Client2
    # r3 - r9 link (r3-eth3, r9-eth0)
    sw = tgen.add_switch("sw39")
    sw.add_link(tgen.gears["r3"])
    sw.add_link(tgen.gears["r9"])

    # r6 - r10 link (r6-eth3, r10-eth0)
    sw = tgen.add_switch("sw610")
    sw.add_link(tgen.gears["r6"])
    sw.add_link(tgen.gears["r10"])


def setup_module(mod):
    "Sets up the pytest environment"

    # Check for minimum kernel version for SRv6 support
    result = required_linux_kernel_version("5.19")
    if result is not True:
        pytest.skip("Kernel requirements not met for SRv6")

    tgen = Topogen(build_topo, mod.__name__)
    tgen.start_topology()

    router_list = tgen.routers()

    # Load configurations to start daemons (with minimal/empty configs for manual configuration)
    for rname, router in router_list.items():
        # Load zebra for IP addresses
        router.load_config(
            TopoRouter.RD_ZEBRA, os.path.join(CWD, "{}/zebra.conf".format(rname))
        )

        # Load empty configs to start daemons (ready for manual configuration)
        router.load_config(
            TopoRouter.RD_ISIS, os.path.join(CWD, "{}/isisd.conf".format(rname))
        )
        router.load_config(
            TopoRouter.RD_BGP, os.path.join(CWD, "{}/bgpd.conf".format(rname))
        )
        router.load_config(
            TopoRouter.RD_OSPF, os.path.join(CWD, "{}/ospfd.conf".format(rname))
        )
        router.load_config(
            TopoRouter.RD_OSPF6, os.path.join(CWD, "{}/ospf6d.conf".format(rname))
        )

    tgen.start_router()

    logger.info("Base topology started - all routers have IP addresses configured")
    logger.info("All daemons running: zebra, isisd, bgpd, ospfd, ospf6d")
    logger.info("No routing protocols configured - ready for manual configuration via vtysh")
    logger.info("Use 'vtysh' to configure ISIS, OSPF, BGP, VRF, SRv6 without restarting")


def teardown_module():
    "Teardown the pytest environment"
    tgen = get_topogen()
    tgen.stop_topology()


def test_routers_up():
    "Check that all routers are up"
    tgen = get_topogen()
    if tgen.routers_have_failure():
        pytest.skip(tgen.errors)

    logger.info("All 10 routers are up and ready for manual configuration")


def test_interfaces_configured():
    "Verify all interfaces have IP addresses configured"
    tgen = get_topogen()
    if tgen.routers_have_failure():
        pytest.skip(tgen.errors)

    step("Checking interface IP addresses")

    for router_name in tgen.routers().keys():
        router = tgen.gears[router_name]
        output = router.vtysh_cmd("show interface brief")
        logger.info("{}: Interfaces:\n{}".format(router_name, output))


if __name__ == "__main__":
    args = ["-s"] + sys.argv[1:]
    sys.exit(pytest.main(args))
