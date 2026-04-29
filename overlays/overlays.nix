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
