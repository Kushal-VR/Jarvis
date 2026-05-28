# Jarvis Sandbox Workspace

This folder is the designated secure sandbox for all filesystem operations executed by Jarvis.
Any file creations, read queries, writes, code generation, and repository integrations must reside inside this path:
`d:\My Projects Dekstop\Jarvis\jarvis\workspace\`

Any attempt by Jarvis to write or edit files outside this folder will be blocked by the `SecuritySandbox` component.
