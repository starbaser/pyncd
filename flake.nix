{
  description = "pyncd, the algebra of neural circuit diagrams and its PyTorch compiler";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";

    pyproject-nix = {
      url = "github:pyproject-nix/pyproject.nix";
      inputs.nixpkgs.follows = "nixpkgs";
    };

    uv2nix = {
      url = "github:pyproject-nix/uv2nix";
      inputs.pyproject-nix.follows = "pyproject-nix";
      inputs.nixpkgs.follows = "nixpkgs";
    };

    pyproject-build-systems = {
      url = "github:pyproject-nix/build-system-pkgs";
      inputs.pyproject-nix.follows = "pyproject-nix";
      inputs.uv2nix.follows = "uv2nix";
      inputs.nixpkgs.follows = "nixpkgs";
    };

    # The page the wheel carries, built by tsncd's own flake.
    tsncd = {
      url = "github:starbaser/tsncd/main";
      inputs.nixpkgs.follows = "nixpkgs";
    };
  };

  outputs =
    {
      self,
      nixpkgs,
      uv2nix,
      pyproject-nix,
      pyproject-build-systems,
      tsncd,
      ...
    }:
    let
      inherit (nixpkgs) lib;
      forAllSystems = lib.genAttrs [
        "x86_64-linux"
        "aarch64-linux"
      ];

      workspace = uv2nix.lib.workspace.loadWorkspace { workspaceRoot = ./.; };
      overlay = workspace.mkPyprojectOverlay { sourcePreference = "wheel"; };

      pythonSetFor =
        system:
        let
          pkgs = nixpkgs.legacyPackages.${system};
          bundle = tsncd.packages.${system}.bundle;
          # The wheel build copies tsncd's Nix output in place of cloning and
          # building the page with npm, which the sandbox could not do. The check
          # environment holds the PyPI torch wheel and the CUDA libraries beside
          # it, which torch loads from its own site-packages at import, so the
          # libraries the host driver would supply are left unpatched and the
          # validators run on the CPU. A consumer that runs on a GPU gives those
          # libraries the driver runpath in its own flake.
          pyprojectOverrides =
            final: prev:
            let
              cudaLibraryNames = builtins.filter (name: lib.hasPrefix "nvidia-" name) (
                builtins.attrNames prev
              );
            in
            {
              pyncd = prev.pyncd.overrideAttrs (old: {
                PYNCD_TSNCD_BUNDLE = "${bundle}";
                PYNCD_TSNCD_REVISION = tsncd.rev;
                nativeBuildInputs =
                  (old.nativeBuildInputs or [ ]) ++ final.resolveBuildSystem { hatchling = [ ]; };
              });
              torch = prev.torch.overrideAttrs (old: {
                autoPatchelfIgnoreMissingDeps = [ "*" ];
              });
            }
            // lib.genAttrs cudaLibraryNames (
              name:
              prev.${name}.overrideAttrs (old: {
                autoPatchelfIgnoreMissingDeps = [ "*" ];
              })
            );
        in
        (pkgs.callPackage pyproject-nix.build.packages { python = pkgs.python314; }).overrideScope (
          lib.composeManyExtensions [
            pyproject-build-systems.overlays.default
            overlay
            pyprojectOverrides
          ]
        );
    in
    {
      packages = forAllSystems (
        system:
        let
          pythonSet = pythonSetFor system;
          env = pythonSet.mkVirtualEnv "pyncd-env" { pyncd = [ "diagrams" ]; };
          # The environment the validation runner needs: the diagram helper's
          # dependencies and the notebook executor's.
          dev = pythonSet.mkVirtualEnv "pyncd-dev-env" {
            pyncd = [
              "diagrams"
              "dev"
            ];
          };
          # The dev environment with the compiler's dependencies, for the
          # validators that import torch.
          check = pythonSet.mkVirtualEnv "pyncd-check-env" {
            pyncd = [
              "diagrams"
              "dev"
              "torch"
            ];
          };
        in
        {
          inherit env dev check;
          pyncd = pythonSet.pyncd;
          default = env;
        }
      );

      apps = forAllSystems (system: {
        default = {
          type = "app";
          program = "${self.packages.${system}.env}/bin/pyncd-server";
          meta.description = "Run the diagram relay and serve the tsncd page on one port";
        };
      });

      checks = forAllSystems (system: {
        inherit (self.packages.${system}) env;
      });

      devShells = forAllSystems (
        system:
        let
          pkgs = nixpkgs.legacyPackages.${system};
        in
        {
          default = pkgs.mkShell {
            packages = [
              pkgs.python314
              pkgs.uv
            ];
            # An editable install carries no page, so the checkout serves and
            # captures with tsncd's built page from the flake.
            TSNCD_DIST = "${tsncd.packages.${system}.bundle}";
            shellHook = ''
              export UV_PYTHON_PREFERENCE="only-system"
              export UV_PYTHON_DOWNLOADS="never"
              export UV_PYTHON="${pkgs.python314}"
              uv sync --quiet --extra diagrams 2>/dev/null || true
              export VIRTUAL_ENV="$PWD/.venv"
              export PATH="$PWD/.venv/bin:$PATH"
            '';
          };
        }
      );
    };
}
