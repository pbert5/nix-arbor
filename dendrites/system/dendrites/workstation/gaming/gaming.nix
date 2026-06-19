{ pkgs, ... }:
{
  programs.steam.enable = true;

  environment.systemPackages = [
    (pkgs.retroarch.withCores (_: with pkgs.libretro; [
      # # Game engines / misc
      # nxengine        # Cave Story
      # prboom          # Doom
      # scummvm
      # thepowdertoy
      # tic80
      # twenty-fortyeight
      # mrboom
      # easyrpg         # RPG Maker 2000/2003
      # gw              # Game & Watch

      # # 3DO
      # opera

      # # Arcade
      # fbneo
      # mame
      # mame2000
      # mame2003
      # mame2003-plus
      # mame2010
      # #mame2015
      # mame2016
      # same_cdi

      # # Atari
      # atari800        # 5200
      # prosystem       # 7800
      # stella          # 2600
      # stella2014
      # virtualjaguar   # Jaguar
      # handy           # Lynx
      # beetle-lynx

      # # Atari ST
      # hatari

      # # Commodore
      # fmsx            # MSX/MSX2
      # bluemsx
      # puae            # Amiga
      # vice-x64
      # vice-x64dtv
      # vice-x64sc
      # vice-x128
      # vice-xcbm2
      # vice-xcbm5x0
      # vice-xpet
      # vice-xplus4
      # vice-xscpu64
      # vice-xvic
      # o2em            # Odyssey2 / Videopac

      # # DOS
      # dosbox
      # dosbox-pure

      # # Game Boy / GBC
      # gambatte
      # sameboy
      # tgbdual
      # mgba            # also GBA

      # # Game Boy Advance
      # beetle-gba
      # gpsp
      # meteor
      # vba-next
      # vba-m

      # # NES
      # fceumm
      # mesen
      # nestopia
      # quicknes

      # # SNES
      # bsnes
      # bsnes-hd
      # bsnes-mercury
      # bsnes-mercury-balanced
      # bsnes-mercury-performance
      # beetle-supafaust
      # mesen-s
      # snes9x
      # snes9x2002
      # snes9x2005
      # snes9x2005-plus
      # snes9x2010

      # # Virtual Boy
      # beetle-vb

      # # Nintendo 64
      # mupen64plus
      # parallel-n64

      # # Nintendo DS
      # desmume
      # desmume2015
      # melonds

      # # Nintendo 3DS
      # citra

      # # GameCube / Wii
      # dolphin

      # # NEC PC Engine / SuperGrafx / CD
      # beetle-pce
      # beetle-pce-fast
      # beetle-supergrafx

      # # NEC PC-FX
      # beetle-pcfx

      # # Neo Geo / Neo Geo CD / NGP
      # beetle-ngp
      # neocd

      # # Sega
      # blastem         # Genesis
      # genesis-plus-gx
      # picodrive       # Genesis / 32X / CD
      # smsplus-gx      # Master System / Game Gear
      # beetle-saturn
      # yabause         # Saturn
      # flycast         # Dreamcast

      # # Sony PlayStation
      # beetle-psx
      # beetle-psx-hw
      # pcsx-rearmed
      # pcsx2
      # play            # PS2
      # swanstation
      # ppsspp          # PSP

      # # Sinclair
      # eightyone       # ZX81
      # fuse            # ZX Spectrum

      # # Bandai WonderSwan
      # beetle-wswan

      # # Intellivision
      # freeintv

      # # GCE Vectrex
      # vecx

      # # Neko Project II (PC-98)
      # np2kai
    ]))
  ];
}
