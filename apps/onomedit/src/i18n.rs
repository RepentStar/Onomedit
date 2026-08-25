use onomedit_core::config;
use std::sync::atomic::{AtomicU8, Ordering};

static CURRENT_LANGUAGE: AtomicU8 = AtomicU8::new(0);

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Language {
    ZhCn,
    EnUs,
}

impl Language {
    pub fn from_code(code: &str) -> Self {
        match config::normalize_language(code) {
            "en-US" => Self::EnUs,
            _ => Self::ZhCn,
        }
    }

    pub fn code(self) -> &'static str {
        match self {
            Self::ZhCn => "zh-CN",
            Self::EnUs => "en-US",
        }
    }

    pub fn name(self) -> &'static str {
        match self {
            Self::ZhCn => "简体中文",
            Self::EnUs => "English",
        }
    }

    pub fn text(self, source: &'static str) -> &'static str {
        if self == Self::ZhCn {
            return source;
        }
        match source {
            "Onomedit - 批量重命名" => "Onomedit - Batch Rename",
            "就绪（可拖入文件或文件夹）" => "Ready (drop files or folders here)",
            "请先添加文件" => "Add files first",
            "后台线程：准备文件并等待编辑器…" => {
                "Preparing files and waiting for the editor…"
            }
            "后台线程：正在生成重命名计划…" => "Preparing the rename plan…",
            "未配置编辑器，请先在设置中填写编辑器命令" => {
                "No editor is configured; enter an editor command in Settings"
            }
            "预览模式不会执行重命名" => "Preview mode does not rename files",
            "未勾选任何项目" => "No items selected",
            "后台线程：正在执行重命名…" => "Renaming files…",
            "后台线程：正在恢复上次重命名…" => "Restoring the latest rename…",
            "添加文件…" => "Add files…",
            "添加文件夹…" => "Add folder…",
            "从剪贴板" => "From clipboard",
            "剪贴板为空或不可读" => "The clipboard is empty or unreadable",
            "清空" => "Clear",
            "已清空" => "Cleared",
            "恢复上次" => "Restore last",
            "设置…" => "Settings…",
            "路径类型:" => "Path type:",
            "展开子文件夹" => "Expand subfolders",
            "层级:" => "Depth:",
            "开始（打开编辑器）" => "Start (open editor)",
            "直接应用规则（跳过编辑器）" => "Apply rules directly (skip editor)",
            "预览（进入重命名确认）" => "Preview (review rename plan)",
            "文件（将按此顺序写入临时文件）" => {
                "Files (written to the edit file in this order)"
            }
            "拖入文件/文件夹，或使用上方按钮添加" => {
                "Drop files/folders here or use the buttons above"
            }
            "重命名预览" => "Rename Preview",
            "重命名确认" => "Confirm Rename",
            "只读，不会修改文件" => "Read-only; no files will be changed",
            "全选" => "Select all",
            "全不选" => "Select none",
            "关闭预览" => "Close preview",
            "取消" => "Cancel",
            "执行重命名" => "Rename selected",
            "执行" => "Apply",
            "原文件名" => "Original name",
            "新文件名" => "New name",
            "差异" => "Difference",
            "距离" => "Distance",
            "预览已关闭（未执行）" => "Preview closed (not applied)",
            "重命名确认已取消" => "Rename confirmation cancelled",
            "Onomedit 设置" => "Onomedit Settings",
            "保存" => "Save",
            "重置默认" => "Reset defaults",
            "主编辑器命令" => "Primary editor command",
            "备用编辑器命令" => "Fallback editor command",
            "等待超时（秒）" => "Wait timeout (seconds)",
            "多标签编辑器" => "Multi-tab editor",
            "打开编辑器" => "Open editor",
            "应用规则" => "Apply rules",
            "环境变量替换" => "Expand variables",
            "自动替换规则" => "Automatic replacement rules",
            "路径类型" => "Path type",
            "排序依据" => "Sort by",
            "反转顺序" => "Reverse order",
            "展开层级" => "Expansion depth",
            "跳过重命名确认" => "Skip rename confirmation",
            "完成后退出" => "Exit when finished",
            "排除文件" => "Exclude files",
            "排除目录" => "Exclude folders",
            "排除符号链接" => "Exclude symbolic links",
            "排除只读" => "Exclude read-only items",
            "排除隐藏" => "Exclude hidden items",
            "排除系统" => "Exclude system items",
            "显示差异" => "Show differences",
            "显示距离" => "Show distance",
            "安全命名" => "Safe names",
            "语言" => "Language",
            "已取消设置（重置默认未保存）" => {
                "Settings cancelled (defaults were not saved)"
            }
            "设置未更改" => "Settings unchanged",
            "设置已保存" => "Settings saved",
            "目标重名，已中止" => "Duplicate targets; operation cancelled",
            "关闭" => "Close",
            "重命名完成" => "Rename complete",
            "恢复完成" => "Restore complete",
            "等待超时必须是数字" => "Wait timeout must be a number",
            "展开层级必须是整数" => "Expansion depth must be an integer",
            _ => source,
        }
    }
}

pub const ALL_LANGUAGES: [Language; 2] = [Language::ZhCn, Language::EnUs];

pub fn set_current(language: Language) {
    CURRENT_LANGUAGE.store(u8::from(language == Language::EnUs), Ordering::Relaxed);
}

pub fn current() -> Language {
    if CURRENT_LANGUAGE.load(Ordering::Relaxed) == 1 {
        Language::EnUs
    } else {
        Language::ZhCn
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn chooses_supported_catalog() {
        assert_eq!(Language::from_code("en_US"), Language::EnUs);
        assert_eq!(Language::EnUs.text("保存"), "Save");
        assert_eq!(Language::ZhCn.text("保存"), "保存");
    }
}
