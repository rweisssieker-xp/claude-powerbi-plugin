# External Tool Installation

Generate the registration file:

```powershell
.\scripts\New-PowerBIExternalToolRegistration.ps1 -OutputPath .\ClaudePowerBIWorkbench.pbitool.json
```

Generate this file on each workstation or checkout location. The registration stores the absolute path to `Invoke-PowerBIUnifiedReview.ps1` so Power BI Desktop can launch it reliably; external binaries and provider DLLs stay installed locally and are not vendored into this repository.

Install it into the machine-wide Power BI Desktop External Tools folder:

```powershell
.\scripts\Install-PowerBIExternalTool.ps1
```

Remove it again:

```powershell
.\scripts\Uninstall-PowerBIExternalTool.ps1
```

Restart Power BI Desktop after install or uninstall. The External Tools menu is loaded during Desktop startup.

The registration launches `Invoke-PowerBIUnifiedReview.ps1` through `powershell.exe` and writes output to `%TEMP%\ClaudePowerBIUnifiedReview`.
