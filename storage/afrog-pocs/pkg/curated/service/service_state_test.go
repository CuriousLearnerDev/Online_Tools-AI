package service

import (
	"context"
	"testing"
)

func TestRuntimeTimestamps(t *testing.T) {
	tmp := t.TempDir()
	t.Setenv("HOME", tmp)

	s := &Service{cfg: Config{Channel: "stable"}}

	if err := s.updateRuntimeUpdated("/tmp/pocs-curated", "m-1"); err != nil {
		t.Fatalf("updateRuntimeUpdated error: %v", err)
	}
	st1, err := s.Status(context.Background())
	if err != nil {
		t.Fatalf("status error: %v", err)
	}
	if st1.State == nil {
		t.Fatalf("state is nil")
	}
	if st1.State.LastCheckAt.IsZero() || st1.State.LastUpdateAt.IsZero() {
		t.Fatalf("expected non-zero timestamps, got check=%v update=%v", st1.State.LastCheckAt, st1.State.LastUpdateAt)
	}
	prevUpdate := st1.State.LastUpdateAt

	if err := s.updateRuntimeCheck("/tmp/pocs-curated", "m-1", ""); err != nil {
		t.Fatalf("updateRuntimeCheck error: %v", err)
	}
	st2, err := s.Status(context.Background())
	if err != nil {
		t.Fatalf("status error: %v", err)
	}
	if st2.State == nil {
		t.Fatalf("state is nil")
	}
	if st2.State.LastCheckAt.IsZero() {
		t.Fatalf("expected non-zero last_check_at")
	}
	if !st2.State.LastUpdateAt.Equal(prevUpdate) {
		t.Fatalf("expected last_update_at unchanged, prev=%v got=%v", prevUpdate, st2.State.LastUpdateAt)
	}
}
