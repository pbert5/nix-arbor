{ ... }:
{
  boot.loader.grub.enable = true;
  boot.loader.grub.configurationLimit = 10;#TODO: this can be a standard option, but should be able to set in the inventory host entry
}
