-- KakaoTalk 메시지 전송 AppleScript
-- argv: {row_number, message}
-- row_number: 카카오톡 chatrooms 탭에서 고정(Pin)된 채팅방 순서

on run argv
    set rowNum to item 1 of argv as integer
    set msg to item 2 of argv

    tell application "KakaoTalk" to activate
    delay 0.5

    tell application "System Events"
        tell process "KakaoTalk"
            set frontmost to true
            delay 0.3

            -- 윈도우 없으면 열기
            if (count of windows) = 0 then
                try
                    click menu bar item 1 of menu bar 2
                    delay 0.3
                    try
                        click menu item "Open KakaoTalk" of menu 1 of menu bar item 1 of menu bar 2
                    on error
                        click menu item "카카오톡 열기" of menu 1 of menu bar item 1 of menu bar 2
                    end try
                    delay 1
                end try
            end if

            -- 기존 채팅창 닫기
            repeat while (count of windows) > 1
                keystroke "w" using command down
                delay 0.3
            end repeat

            tell window 1
                -- chatrooms 탭 (checkbox 2)
                click checkbox 2
                delay 0.5

                -- 고정된 행 선택
                tell table 1 of scroll area 1
                    select row rowNum
                    delay 0.3
                end tell
            end tell

            -- Enter로 채팅방 열기
            key code 36
            delay 1.5

            -- 채팅창 열렸는지 확인
            if (count of windows) < 2 then
                error "chat window not opened"
            end if

            -- 입력 필드에 직접 값 설정 (AX API)
            tell window 1
                tell scroll area 2
                    set ta to text area 1
                    set value of ta to msg
                    delay 0.3
                end tell
            end tell

            -- Enter로 전송
            key code 36
            delay 0.5

            -- 채팅창 닫기
            keystroke "w" using command down
            delay 0.3
        end tell
    end tell

    return "ok"
end run
