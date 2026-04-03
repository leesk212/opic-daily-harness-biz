#!/bin/bash
# KakaoTalk 메시지 전송 스크립트 (AppleScript UI 자동화)
# Usage: kakao_send.sh --me "message"        # 나와의 채팅
#        kakao_send.sh "chatname" "message"   # 특정 채팅방

set -e

SELF_MODE=false
CHAT_NAME=""
MESSAGE=""

if [ "$1" = "--me" ]; then
    SELF_MODE=true
    MESSAGE="$2"
else
    CHAT_NAME="$1"
    MESSAGE="$2"
fi

if [ -z "$MESSAGE" ]; then
    echo "Usage: $0 --me \"message\" OR $0 \"chatname\" \"message\"" >&2
    exit 1
fi

# 1. 카카오톡 메인 윈도우 열기
osascript -e '
tell application "System Events"
    tell process "KakaoTalk"
        try
            click menu bar item 1 of menu bar 2
            delay 0.3
            click menu item "Open KakaoTalk" of menu 1 of menu bar item 1 of menu bar 2
        on error
            try
                click menu item "카카오톡 열기" of menu 1 of menu bar item 1 of menu bar 2
            end try
        end try
    end tell
end tell
' 2>/dev/null

sleep 1

if [ "$SELF_MODE" = true ]; then
    # 나와의 채팅: friends 탭 → 내 프로필(첫번째 row) 더블클릭 → 나와의 채팅 버튼
    osascript << 'EOF'
tell application "KakaoTalk" to activate
delay 0.5

tell application "System Events"
    tell process "KakaoTalk"
        set frontmost to true
        delay 0.3

        -- friends 탭 전환
        tell window 1
            repeat with cb in (every checkbox)
                if description of cb is "toggle button" then
                    -- 첫번째 체크박스가 friends
                end if
            end repeat
        end tell

        -- Escape로 현재 상태 초기화
        key code 53
        delay 0.3
    end tell
end tell
EOF

    # chatrooms 탭으로 이동 후 "나와의 채팅" 또는 계정 이름으로 검색
    # Accessibility API 대신 키보드 네비게이션 사용
    osascript << ASCRIPT
tell application "KakaoTalk" to activate
delay 0.3

tell application "System Events"
    tell process "KakaoTalk"
        set frontmost to true
        delay 0.2

        -- Cmd+Shift+F: 전체 검색 (카카오톡 내장)
        -- 안되면 그냥 chatrooms 탭에서 첫번째 행
    end tell
end tell
ASCRIPT

else
    echo "Non-self chat not implemented yet" >&2
    exit 1
fi
