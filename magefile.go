//go:build mage

package main

import (
	"archive/zip"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"runtime"
	"strings"
	"time"
)

const (
	addonDir = "wbc3_sprite_tools"
	binDir   = "bin"
	zipName  = "wbc3_sprite_tools.zip"
	venvDir  = ".venv"
)

type fileState struct {
	modTime time.Time
	size    int64
}

// Build packages the Blender add-on into bin/wbc3_sprite_tools.zip.
func Build() error {
	outputPath := filepath.Join(binDir, zipName)
	if err := os.MkdirAll(binDir, 0o755); err != nil {
		return err
	}

	if err := os.Remove(outputPath); err != nil && !os.IsNotExist(err) {
		return err
	}

	output, err := os.Create(outputPath)
	if err != nil {
		return err
	}
	defer output.Close()

	writer := zip.NewWriter(output)
	defer writer.Close()

	if err := filepath.WalkDir(addonDir, func(path string, entry os.DirEntry, walkErr error) error {
		if walkErr != nil {
			return walkErr
		}
		if shouldSkip(path, entry) {
			if entry.IsDir() {
				return filepath.SkipDir
			}
			return nil
		}
		if entry.IsDir() {
			return nil
		}
		return addFile(writer, path)
	}); err != nil {
		return err
	}

	fmt.Printf("Wrote %s\n", outputPath)
	return nil
}

// Watch rebuilds the Blender add-on zip when watched Python files change.
func Watch() error {
	watchDirs, err := pythonDirs(".")
	if err != nil {
		return err
	}
	if len(watchDirs) == 0 {
		return fmt.Errorf("no directories with Python files found")
	}

	fmt.Println("Watching Python files in:")
	for _, dir := range watchDirs {
		fmt.Printf("  %s\n", dir)
	}
	fmt.Println("Press Ctrl+C to stop.")

	if err := Build(); err != nil {
		return err
	}

	previous, err := snapshotPythonFiles(watchDirs)
	if err != nil {
		return err
	}

	for {
		time.Sleep(1 * time.Second)

		current, err := snapshotPythonFiles(watchDirs)
		if err != nil {
			fmt.Printf("watch scan failed: %v\n", err)
			continue
		}
		if !changed(previous, current) {
			continue
		}

		fmt.Printf("Change detected at %s\n", time.Now().Format("15:04:05"))
		if err := Build(); err != nil {
			fmt.Printf("build failed: %v\n", err)
			continue
		}
		previous = current
	}
}

// Pylance creates a local Python environment with Blender API stubs.
func Pylance() error {
	python := "python"
	if runtime.GOOS == "windows" {
		python = "py"
	}

	if _, err := os.Stat(venvDir); os.IsNotExist(err) {
		if err := run(python, "-m", "venv", venvDir); err != nil {
			return err
		}
	}

	pip := filepath.Join(venvDir, "bin", "pip")
	if runtime.GOOS == "windows" {
		pip = filepath.Join(venvDir, "Scripts", "pip.exe")
	}

	if err := run(pip, "install", "-r", "requirements-dev.txt"); err != nil {
		return err
	}

	fmt.Println("Pylance support ready. Reload VS Code if imports are still unresolved.")
	return nil
}

func run(name string, args ...string) error {
	fmt.Printf("%s %s\n", name, strings.Join(args, " "))
	process, err := os.StartProcess(name, append([]string{name}, args...), &os.ProcAttr{
		Files: []*os.File{os.Stdin, os.Stdout, os.Stderr},
	})
	if err != nil {
		return err
	}
	state, err := process.Wait()
	if err != nil {
		return err
	}
	if !state.Success() {
		return fmt.Errorf("%s failed: %s", name, state.String())
	}
	return nil
}

func pythonDirs(root string) ([]string, error) {
	dirs := map[string]struct{}{}
	err := filepath.WalkDir(root, func(path string, entry os.DirEntry, walkErr error) error {
		if walkErr != nil {
			return walkErr
		}
		if entry.IsDir() {
			if shouldSkipDir(path, entry.Name()) {
				return filepath.SkipDir
			}
			return nil
		}
		if strings.EqualFold(filepath.Ext(path), ".py") {
			dirs[filepath.Dir(path)] = struct{}{}
		}
		return nil
	})
	if err != nil {
		return nil, err
	}

	result := make([]string, 0, len(dirs))
	for dir := range dirs {
		result = append(result, dir)
	}
	sortStrings(result)
	return result, nil
}

func snapshotPythonFiles(dirs []string) (map[string]fileState, error) {
	snapshot := map[string]fileState{}
	for _, dir := range dirs {
		err := filepath.WalkDir(dir, func(path string, entry os.DirEntry, walkErr error) error {
			if walkErr != nil {
				return walkErr
			}
			if entry.IsDir() {
				if path != dir && shouldSkipDir(path, entry.Name()) {
					return filepath.SkipDir
				}
				return nil
			}
			if !strings.EqualFold(filepath.Ext(path), ".py") {
				return nil
			}
			info, err := entry.Info()
			if err != nil {
				return err
			}
			snapshot[path] = fileState{modTime: info.ModTime(), size: info.Size()}
			return nil
		})
		if err != nil {
			return nil, err
		}
	}
	return snapshot, nil
}

func changed(previous, current map[string]fileState) bool {
	if len(previous) != len(current) {
		return true
	}
	for path, previousState := range previous {
		currentState, ok := current[path]
		if !ok {
			return true
		}
		if !previousState.modTime.Equal(currentState.modTime) || previousState.size != currentState.size {
			return true
		}
	}
	return false
}

func shouldSkipDir(path string, name string) bool {
	switch name {
	case ".git", "bin", "__pycache__":
		return true
	}
	return false
}

func sortStrings(values []string) {
	for i := 1; i < len(values); i++ {
		for j := i; j > 0 && values[j] < values[j-1]; j-- {
			values[j], values[j-1] = values[j-1], values[j]
		}
	}
}

func shouldSkip(path string, entry os.DirEntry) bool {
	name := entry.Name()
	if name == "__pycache__" || name == ".DS_Store" {
		return true
	}
	return strings.HasSuffix(name, ".pyc")
}

func addFile(writer *zip.Writer, path string) error {
	source, err := os.Open(path)
	if err != nil {
		return err
	}
	defer source.Close()

	info, err := source.Stat()
	if err != nil {
		return err
	}

	header, err := zip.FileInfoHeader(info)
	if err != nil {
		return err
	}
	header.Name = filepath.ToSlash(path)
	header.Method = zip.Deflate

	target, err := writer.CreateHeader(header)
	if err != nil {
		return err
	}

	_, err = io.Copy(target, source)
	return err
}
