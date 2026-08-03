using System;
using System.Diagnostics;
using System.IO;
using System.IO.Compression;
using System.Reflection;
using System.Windows.Forms;

internal static class BootstrapInstalador
{
    private const string ResourceName = "SuiteRrhhInstaller.OfflinePayload.zip";

    [STAThread]
    private static void Main()
    {
        var tempDirectory = Path.Combine(Path.GetTempPath(), "Suite_RRHH_" + Guid.NewGuid().ToString("N"));
        try
        {
            Directory.CreateDirectory(tempDirectory);
            var archivePath = Path.Combine(tempDirectory, "offline_installer_payload.zip");
            using (var resource = Assembly.GetExecutingAssembly().GetManifestResourceStream(ResourceName))
            {
                if (resource == null)
                    throw new InvalidOperationException("No se encontro el contenido interno del instalador.");
                using (var destination = File.Create(archivePath))
                    resource.CopyTo(destination);
            }

            ZipFile.ExtractToDirectory(archivePath, tempDirectory);
            var scriptPath = Path.Combine(tempDirectory, "instalar_rrhh.cmd");
            if (!File.Exists(scriptPath))
                throw new InvalidOperationException("No se encontro el programa de instalacion interno.");

            var process = Process.Start(new ProcessStartInfo
            {
                FileName = Environment.GetEnvironmentVariable("ComSpec") ?? "cmd.exe",
                Arguments = "/c \"" + scriptPath + "\"",
                WorkingDirectory = tempDirectory,
                UseShellExecute = true,
                WindowStyle = ProcessWindowStyle.Normal
            });
            if (process == null)
                throw new InvalidOperationException("No se pudo iniciar la instalacion.");

            process.WaitForExit();
            // El usuario puede cerrar la ventana de CMD tras revisar el progreso.
            // En ese caso Windows devuelve STATUS_CONTROL_C_EXIT; no se muestra un falso error.
            if ((uint)process.ExitCode == 0xC000013A)
                return;

            if (process.ExitCode != 0)
                throw new InvalidOperationException("La instalacion no pudo completarse. Codigo: " + process.ExitCode + ".");

            MessageBox.Show("Suite RRHH se ha instalado correctamente. Se han creado accesos directos en el Escritorio y el menu Inicio.", "Suite RRHH", MessageBoxButtons.OK, MessageBoxIcon.Information);
        }
        catch (Exception exception)
        {
            MessageBox.Show("No se ha podido instalar Suite RRHH.\r\n\r\n" + exception.Message, "Suite RRHH - Error de instalacion", MessageBoxButtons.OK, MessageBoxIcon.Error);
            Environment.ExitCode = 1;
        }
        finally
        {
            try
            {
                if (Directory.Exists(tempDirectory))
                    Directory.Delete(tempDirectory, true);
            }
            catch { }
        }
    }
}
