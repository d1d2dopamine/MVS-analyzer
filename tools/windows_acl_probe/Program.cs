using System.Security.AccessControl;
using System.Security.Principal;
using System.Text.Json;

// Read-only, framework-only witness independent of the Python Win32 backend.
// The caller supplies one absolute path to its own temporary directory fixture.
if (!OperatingSystem.IsWindows())
{
    Console.Error.WriteLine("WindowsAclProbe requires Windows.");
    return 2;
}

try
{
    if (args.Length != 1 || !Path.IsPathFullyQualified(args[0]))
        throw new ArgumentException("Expected one absolute fixture directory path.");

    var directory = new DirectoryInfo(args[0]);
    if (!directory.Exists)
        throw new DirectoryNotFoundException("Fixture directory does not exist.");

    const AccessControlSections sections = AccessControlSections.Owner
        | AccessControlSections.Group | AccessControlSections.Access;
    var acl = directory.GetAccessControl(sections);
    using var identity = WindowsIdentity.GetCurrent();
    var user = identity.User?.Value
        ?? throw new InvalidOperationException("Current user SID is unavailable.");
    var owner = acl.GetOwner(typeof(SecurityIdentifier))?.Value
        ?? throw new InvalidOperationException("Owner SID is unavailable.");
    var sddl = acl.GetSecurityDescriptorSddlForm(sections);
    if (string.IsNullOrWhiteSpace(sddl))
        throw new InvalidOperationException("Security descriptor is empty.");
    var rules = new List<object>();
    foreach (FileSystemAccessRule rule in acl.GetAccessRules(true, true, typeof(SecurityIdentifier)))
    {
        rules.Add(new
        {
            Sid = rule.IdentityReference.Value,
            Type = rule.AccessControlType.ToString(),
            Inherited = rule.IsInherited,
            Rights = rule.FileSystemRights.ToString(),
            RightsMask = (int)rule.FileSystemRights,
            Inheritance = rule.InheritanceFlags.ToString(),
            Propagation = rule.PropagationFlags.ToString()
        });
    }
    // Emit only after every read and conversion has succeeded.
    Console.WriteLine(JsonSerializer.Serialize(new
    {
        Protected = acl.AreAccessRulesProtected,
        User = user,
        Owner = owner,
        Rules = rules,
        Sddl = sddl
    }));
    return 0;
}
catch (Exception error)
{
    Console.Error.WriteLine($"WindowsAclProbe: {error.GetType().Name}: {error.Message}");
    return 1;
}
