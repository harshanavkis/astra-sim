# The one nix environment for E8: builds and runs of astra-sim-fresh (analytical
# and ns-3 backends) and the Opus symbolic_tensor_graph trace generator.
# GC root (keeps every input in the store across garbage collections):
#   nix-build /scratch/harshanavkis/loom-proj/e8-astrasim/shell.nix -A inputDerivation -o /scratch/harshanavkis/loom-proj/e8-astrasim/.gcroots/shell
# Use: nix-shell /scratch/harshanavkis/loom-proj/e8-astrasim/shell.nix [--run CMD]
{ pkgs ? import <nixpkgs> {} }:
let
  py = pkgs.python312.withPackages (ps: with ps; [ numpy sympy pandas tqdm pyyaml protobuf graphviz matplotlib ]);
  libs = [ pkgs.protobuf_29 pkgs.abseil-cpp_202407 pkgs.openmpi pkgs.zlib ];
in pkgs.mkShell {
  packages = [ pkgs.cmake pkgs.gnumake pkgs.git pkgs.pkg-config pkgs.time pkgs.rclone pkgs.boost py ] ++ libs;
  PROTOBUF_FROM_SOURCE = "True";
  # build: cxxopts needs stdint.h under gcc 15; run: the ns-3 binary has no rpath to libs
  shellHook = ''
    export E8_SHELL=1
    export NIX_CFLAGS_COMPILE="$NIX_CFLAGS_COMPILE -include stdint.h"
    export LD_LIBRARY_PATH=${pkgs.lib.makeLibraryPath libs}''${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}
  '';
}
