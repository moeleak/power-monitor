{
  description = "Nix flake for testing the power monitor script locally";

  inputs.nixpkgs.url = "github:NixOS/nixpkgs/nixos-24.05";

  outputs = { self, nixpkgs }:
    let
      systems = [
        "x86_64-linux"
        "aarch64-linux"
        "x86_64-darwin"
        "aarch64-darwin"
      ];
      forAllSystems = nixpkgs.lib.genAttrs systems;
      mkPkgs = system: import nixpkgs { inherit system; };
      mkPythonEnv = pkgs:
        pkgs.python311.withPackages (ps: with ps; [
          requests
          beautifulsoup4
          pyyaml
        ]);
    in {
      formatter = forAllSystems (system:
        let pkgs = mkPkgs system;
        in pkgs.nixpkgs-fmt);

      devShells = forAllSystems (system:
        let
          pkgs = mkPkgs system;
          pythonEnv = mkPythonEnv pkgs;
        in {
          default = pkgs.mkShell {
            packages = [
              pythonEnv
              pkgs.just
            ];
            POWER_MONITOR_URL =
              "https://www.wap.ekm365.com/nat/pay.aspx?mid=20710001759";
            shellHook = ''
              echo "Power monitor environment ready. Run:"
              echo "  python scripts/check_power.py --format json"
            '';
          };
        });

      apps = forAllSystems (system:
        let
          pkgs = mkPkgs system;
          pythonEnv = mkPythonEnv pkgs;
          runner = pkgs.writeShellScriptBin "power-monitor" ''
            exec ${pythonEnv}/bin/python ${self}/scripts/check_power.py "$@"
          '';
        in {
          default = {
            type = "app";
            program = "${runner}/bin/power-monitor";
          };
        });

      checks = forAllSystems (system:
        let
          pkgs = mkPkgs system;
          pythonEnv = mkPythonEnv pkgs;
        in {
          syntax = pkgs.runCommand "power-monitor-syntax" {
            buildInputs = [ pythonEnv ];
          } ''
            cp -r ${self}/scripts ./scripts
            chmod -R +w scripts
            ${pythonEnv}/bin/python -m compileall scripts
            touch $out
          '';
        });
    };
}
