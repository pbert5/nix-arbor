Yes, for a fully Nix-managed fleet, **multicast autoconf is mostly redundant**.

Yggdrasil only needs either **static peers** or **multicast discovery on the same subnet** to get connected, and it **never auto-adds remote Internet peers** anyway. So if your flake already declares each machine’s peers, listeners, and key policy, then the zero-config part is not buying you much except convenience on a trusted local segment. ([Yggdrasil Network][1])

My recommendation for machines you control is:

* use **static `Peers`**
* keep `Listen` empty unless a node really needs inbound peering
* disable or tightly scope `MulticastInterfaces`
* populate `AllowedPublicKeys`
* firewall the Yggdrasil interface

That gives you a predictable, declarative mesh that matches how you already think about NixOS. Also, `AllowedPublicKeys` only controls who may form a peering session. It is **not** a service firewall, so open ports on the Yggdrasil interface still need normal IPv6 firewall rules. ([Yggdrasil Network][2])

On the multiple-instance question, **yes, you can run multiple Yggdrasil instances**, but there is an important catch. A maintainer-confirmed answer says you can run as many instances as you want, but **only one should have TUN enabled in a given network namespace**, otherwise the `200::/7` routes conflict. The documented way to avoid that is setting `IfName: none` on the extra instance so it runs in headless router mode, and each instance also needs its own admin socket because the default admin endpoint is shared. ([GitHub][3])

So the sane patterns are:

* **one normal Yggdrasil instance with a TUN** for the network you actually use locally
* optional **second headless instance** with `IfName: none` if you need a separate peering/routing role
* or put the second full instance in a **separate network namespace, container, or VM** if you really need another TUN-bearing overlay on the same host

That last part is partly an inference from the maintainer guidance about per-namespace route conflicts, not an official how-to. ([GitHub][3])

For your trust model, I would separate the ideas like this:

### Best model for a private, trusted mesh

Use **one private Yggdrasil overlay over Tailscale or WireGuard reachability**, with only your own nodes as peers, no public peers, and no multicast except maybe on a dedicated trusted VLAN. Since Yggdrasil can peer over reachable IPv4 or IPv6 networks and works alongside many VPNs, using Tailscale as the underlay is a clean fit. ([Yggdrasil Network][1])

### Best model if you also want access to public Yggdrasil

Do **not** treat the same Yggdrasil instance as both your trusted internal fabric and your public-exposure fabric. Once an instance is connected into the wider network, your node is typically routable from other Yggdrasil nodes, and Yggdrasil’s own docs tell you to use a firewall and not expose services you do not want reachable. ([Yggdrasil Network][1])

If you want both private and public access, the cleaner order is:

1. **Private instance only**, for your actual machine-to-machine trust.
2. Separate **public instance or public gateway**, ideally in a VM/container/netns or on a different machine.
3. Strict firewalling between those two roles.

That is better than relying on “public Yggdrasil for discovery, VPN for trust” unless you specifically need Yggdrasil’s overlay behavior for something. If all your nodes already have Tailscale, then Tailscale already gives you authenticated reachability and ACLs. In that case, Yggdrasil should only stay if you want its mesh routing model, stable overlay identities, or local subnet auto-meshing. ([Yggdrasil Network][1])

One subtle but important point: **passworded peerings or multicast passwords are not the same as isolation**. The Yggdrasil v0.5 notes explicitly say that password restrictions do **not** create network isolation, because reachability is still transitive. So if an instance touches the public network, do not think of passwording as making that instance “private.” ([Yggdrasil Network][4])

So my actual opinion for your setup is:

* For your own fleet, **static flake-defined Yggdrasil over Tailscale** is the cleanest.
* Disable multicast on normal LANs, or only enable it on a dedicated trusted segment.
* Use `AllowedPublicKeys` plus a firewall.
* Keep public-network access **separate** from your trusted internal instance.
* If you do not have a concrete reason to join the public Yggdrasil network, **do not join it**.

That is the least messy and most Nix-aligned design. ([Yggdrasil Network][1])

I can sketch a concrete NixOS pattern next, like **private Ygg over Tailscale, optional public headless instance, and firewall rules**.

[1]: https://yggdrasil-network.github.io/faq.html "FAQ | Yggdrasil Network"
[2]: https://yggdrasil-network.github.io/configurationref.html?utm_source=chatgpt.com "Configuration Reference"
[3]: https://github.com/yggdrasil-network/yggdrasil-go/discussions/1295 "Ability to run multiple instances of Ygg router at the same machine · yggdrasil-network yggdrasil-go · Discussion #1295 · GitHub"
[4]: https://yggdrasil-network.github.io/2023/10/22/upcoming-v05-release.html?utm_source=chatgpt.com "Upcoming v0.5 Release"
