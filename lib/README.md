# lib — compile-time Siemens.Engineering.dll override

This machine does not need TIA Portal installed to **build** Openn2 — but the
compiler needs a `Siemens.Engineering.dll` to reference. Drop one here:

```
lib\Siemens.Engineering.dll
```

- Take it from any machine with TIA Portal installed, preferably **V18** (the
  oldest supported version, for maximum runtime compatibility):
  `C:\Program Files\Siemens\Automation\Portal V18\PublicAPI\V18\Siemens.Engineering.dll`
- V19 or V20 also work as a compile reference.
- The DLL is only used at compile time. At runtime the app discovers the TIA
  Portal versions installed on the target machine (V18–V20), lets the user pick
  one at startup, and loads that version's assemblies — see
  `03_ApiManager\OpennessSetup.cs`.
- The DLL is **not** copied to the output folder and must not be committed to
  git (it is Siemens-proprietary; `.gitignore` excludes it).

On machines that *do* have TIA Portal V18–V20 installed, this folder can stay
empty — the project file finds the installed PublicAPI DLL via the registry.
