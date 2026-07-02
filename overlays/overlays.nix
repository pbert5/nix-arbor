final: prev:
let
	lib = final.lib;
	existingCFlags = old:
		if old ? NIX_CFLAGS_COMPILE then
			if builtins.isList old.NIX_CFLAGS_COMPILE then
				old.NIX_CFLAGS_COMPILE
			else
				[ old.NIX_CFLAGS_COMPILE ]
		else
			[ ];
in
{
	codex-switch = final.writeShellApplication {
		name = "codex-switch";
		runtimeInputs = [ final.python3 ];
		text = ''
			exec ${final.python3}/bin/python ${../tools/codex-switch/codex-switch.py} "$@"
		'';
	};

	btop = prev.btop.overrideAttrs (old: {
		patches = (old.patches or [ ]) ++ [
			./btop-zfs-pool-space.patch
		];

		meta = (old.meta or { }) // {
			description = lib.concatStringsSep " " [
				((old.meta.description or "Resource monitor"))
				"(patched locally to report ZFS mount space from zfs list)"
			];
		};
	});

	mtx = prev.mtx.overrideAttrs (old: {
		NIX_CFLAGS_COMPILE = existingCFlags old ++ [ "-std=gnu17" ];

		meta = (old.meta or { }) // {
			description = lib.concatStringsSep " " [
				((old.meta.description or "Media Changer Tools"))
				"(patched locally to avoid C23 false/true keyword breakage)"
			];
		};
	});
}
