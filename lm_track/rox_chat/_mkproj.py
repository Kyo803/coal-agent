from sandbox import sb

sb.write("/home/rox/work/testproj/main.py",
         "def main():\n    return 1 + 1\n\n\nif __name__ == '__main__':\n"
         "    print(main())\n")
print(sb.shell("ls -la /home/rox/work/testproj")["out"])
