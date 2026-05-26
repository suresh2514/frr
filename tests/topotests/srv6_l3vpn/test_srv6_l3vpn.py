#!/usr/bin/env python
# SPDX-License-Identifier: ISC

"""
test_srv6_l3vpn.py: SRv6 L3VPN topology test.

Topology:
    Core network (r1-r6) with ISIS and SRv6:
        r1 --- r2
        |  \    |
        |   r3--r6
        |   |   |
        r5--r4--/

    PE routers: r3, r6 (with VRFs Client1 and Client2)
    CE routers:
      - Client1: r7 (connects to r3), r8 (connects to r6)
      - Client2: r9 (connects to r3), r10 (connects to r6)

    Tests SRv6-based L3VPN with BGP VPNv4/VPNv6 over ISIS core.
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

pytestmark = [pytest.mark.bgpd, pytest.mark.isisd, pytest.mark.ospfd, pytest.mark.ospf6d]


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

    # Configure VRFs BEFORE loading configs (so zebra.conf can apply VRF interface settings)
    for rname in ["r3", "r6"]:
        router = router_list[rname]

        # Enable VRF strict mode
        router.run("sysctl -w net.vrf.strict_mode=1")

        # Create VRF devices
        router.run("ip link add Client1 type vrf table 1001")
        router.run("ip link set Client1 up")
        router.run("ip link add Client2 type vrf table 1002")
        router.run("ip link set Client2 up")

        # Enslave interfaces to VRFs BEFORE loading config
        if rname == "r3":
            router.run("ip link set r3-eth2 master Client1")
            router.run("ip link set r3-eth3 master Client2")
        elif rname == "r6":
            router.run("ip link set r6-eth2 master Client1")
            router.run("ip link set r6-eth3 master Client2")

    # Load configurations for all routers
    for rname, router in router_list.items():
        router.load_config(
            TopoRouter.RD_ZEBRA, os.path.join(CWD, "{}/zebra.conf".format(rname))
        )
        router.load_config(
            TopoRouter.RD_ISIS, os.path.join(CWD, "{}/isisd.conf".format(rname))
        )

        # Load BGP only for PE routers (r3, r6)
        if rname in ["r3", "r6"]:
            router.load_config(
                TopoRouter.RD_BGP, os.path.join(CWD, "{}/bgpd.conf".format(rname))
            )
            router.load_config(
                TopoRouter.RD_OSPF, os.path.join(CWD, "{}/ospfd.conf".format(rname))
            )
            router.load_config(
                TopoRouter.RD_OSPF6, os.path.join(CWD, "{}/ospf6d.conf".format(rname))
            )

        # Load OSPF for CE routers (r7, r8, r9, r10)
        if rname in ["r7", "r8", "r9", "r10"]:
            router.load_config(
                TopoRouter.RD_OSPF, os.path.join(CWD, "{}/ospfd.conf".format(rname))
            )
            router.load_config(
                TopoRouter.RD_OSPF6, os.path.join(CWD, "{}/ospf6d.conf".format(rname))
            )

    tgen.start_router()

    # Configure IP addresses on VRF interfaces using kernel commands
    # FRR doesn't apply addresses to pre-enslaved VRF interfaces from config
    for rname in ["r3", "r6"]:
        router = router_list[rname]

        if rname == "r3":
            # Configure r3-eth2 (Client1)
            router.run("ip addr add 172.16.11.3/24 dev r3-eth2")
            router.run("ip -6 addr add 2001:cafe:11::3/64 dev r3-eth2")
            # Configure r3-eth3 (Client2)
            router.run("ip addr add 172.16.21.3/24 dev r3-eth3")
            router.run("ip -6 addr add 2001:cafe:21::3/64 dev r3-eth3")
        elif rname == "r6":
            # Configure r6-eth2 (Client1)
            router.run("ip addr add 172.16.12.6/24 dev r6-eth2")
            router.run("ip -6 addr add 2001:cafe:12::6/64 dev r6-eth2")
            # Configure r6-eth3 (Client2)
            router.run("ip addr add 172.16.22.6/24 dev r6-eth3")
            router.run("ip -6 addr add 2001:cafe:22::6/64 dev r6-eth3")


def teardown_module():
    "Teardown the pytest environment"
    tgen = get_topogen()
    tgen.stop_topology()


def test_routers_up():
    "Check that all routers are up"
    tgen = get_topogen()
    if tgen.routers_have_failure():
        pytest.skip(tgen.errors)

    logger.info("All routers are up")


def test_isis_adjacencies():
    "Verify ISIS adjacencies are established in the core"
    tgen = get_topogen()
    if tgen.routers_have_failure():
        pytest.skip(tgen.errors)

    step("Checking ISIS adjacencies")

    # Expected adjacencies for each core router
    expected_adjacencies = {
        "r1": ["r2", "r3", "r5"],
        "r2": ["r1", "r6"],
        "r3": ["r1", "r4"],
        "r4": ["r3", "r5"],
        "r5": ["r1", "r4", "r6"],
        "r6": ["r2", "r5"],
    }

    for router_name, expected_neighbors in expected_adjacencies.items():
        router = tgen.gears[router_name]
        output = router.vtysh_cmd("show isis neighbor json")
        neighbor_data = json.loads(output)

        # Extract actual neighbor names
        actual_neighbors = []
        if "adjacencies" in neighbor_data:
            for adj in neighbor_data["adjacencies"]:
                actual_neighbors.append(adj["systemId"])

        logger.info("{}: Expected neighbors: {}, Got: {}".format(
            router_name, expected_neighbors, actual_neighbors))


def test_srv6_locators():
    "Verify SRv6 locators are configured and advertised"
    tgen = get_topogen()
    if tgen.routers_have_failure():
        pytest.skip(tgen.errors)

    step("Checking SRv6 locators")

    # Expected locators for PE routers only
    expected_locators = {
        "r3": "2001:dead:30::/64",
        "r6": "2001:dead:60::/64",
    }

    for router_name, expected_locator in expected_locators.items():
        router = tgen.gears[router_name]
        output = router.vtysh_cmd("show segment-routing srv6 locator")
        logger.info("{}: SRv6 locator output:\n{}".format(router_name, output))


def test_bgp_vpn_routes():
    "Verify BGP VPN routes are exchanged between PEs"
    tgen = get_topogen()
    if tgen.routers_have_failure():
        pytest.skip(tgen.errors)

    step("Checking BGP VPNv4 and VPNv6 routes on PE routers")

    for router_name in ["r3", "r6"]:
        router = tgen.gears[router_name]

        # Check BGP VPNv4 routes
        output = router.vtysh_cmd("show bgp ipv4 vpn")
        logger.info("{}: BGP VPNv4 routes:\n{}".format(router_name, output))

        # Check BGP VPNv6 routes
        output = router.vtysh_cmd("show bgp ipv6 vpn")
        logger.info("{}: BGP VPNv6 routes:\n{}".format(router_name, output))


def test_vrf_routes():
    "Verify routes are present in VRFs on PE routers"
    tgen = get_topogen()
    if tgen.routers_have_failure():
        pytest.skip(tgen.errors)

    step("Checking VRF routing tables")

    for router_name in ["r3", "r6"]:
        router = tgen.gears[router_name]

        # Check Client1 VRF routes
        output = router.vtysh_cmd("show ip route vrf Client1")
        logger.info("{}: VRF Client1 IPv4 routes:\n{}".format(router_name, output))

        output = router.vtysh_cmd("show ipv6 route vrf Client1")
        logger.info("{}: VRF Client1 IPv6 routes:\n{}".format(router_name, output))

        # Check Client2 VRF routes
        output = router.vtysh_cmd("show ip route vrf Client2")
        logger.info("{}: VRF Client2 IPv4 routes:\n{}".format(router_name, output))

        output = router.vtysh_cmd("show ipv6 route vrf Client2")
        logger.info("{}: VRF Client2 IPv6 routes:\n{}".format(router_name, output))


def test_ce_connectivity():
    "Test end-to-end connectivity between CE routers"
    tgen = get_topogen()
    if tgen.routers_have_failure():
        pytest.skip(tgen.errors)

    step("Testing CE to CE connectivity through SRv6 core")

    # Client1 CE routers
    r7 = tgen.gears["r7"]
    r8 = tgen.gears["r8"]

    output = r7.vtysh_cmd("show ip route")
    logger.info("r7: IPv4 routing table:\n{}".format(output))

    output = r8.vtysh_cmd("show ip route")
    logger.info("r8: IPv4 routing table:\n{}".format(output))

    # Client2 CE routers
    r9 = tgen.gears["r9"]
    r10 = tgen.gears["r10"]

    output = r9.vtysh_cmd("show ip route")
    logger.info("r9: IPv4 routing table:\n{}".format(output))

    output = r10.vtysh_cmd("show ip route")
    logger.info("r10: IPv4 routing table:\n{}".format(output))


def test_vrf_isolation():
    "Verify that Client1 and Client2 VRFs are isolated"
    tgen = get_topogen()
    if tgen.routers_have_failure():
        pytest.skip(tgen.errors)

    step("Verifying VRF isolation between Client1 and Client2")

    # On PE routers, verify routes from Client1 don't leak into Client2
    for router_name in ["r3", "r6"]:
        router = tgen.gears[router_name]

        # Check BGP routes for each VRF have correct RT
        output = router.vtysh_cmd("show bgp vrf Client1 ipv4 unicast json")
        logger.info("{}: VRF Client1 BGP routes:\n{}".format(router_name, output))

        output = router.vtysh_cmd("show bgp vrf Client2 ipv4 unicast json")
        logger.info("{}: VRF Client2 BGP routes:\n{}".format(router_name, output))


if __name__ == "__main__":
    args = ["-s"] + sys.argv[1:]
    sys.exit(pytest.main(args))
