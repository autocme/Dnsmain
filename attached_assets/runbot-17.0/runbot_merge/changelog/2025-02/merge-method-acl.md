IMP: allow non-reviewer employees to set the merge method on the PRs they create

Previously this was only allowed for reviewers actual (note: not necessarily
the PR's own), but when the reviewer is busy and the PR is blocked on just the
merge method it can be frustrating. However because the merge method has commit
impliciation via the PR description (squash/merge/rebase-merge) giving access to
any author might be a bit too relaxed.
