!macro customInstall
  CreateShortCut "$DESKTOP\Llama Trainer.lnk" "$INSTDIR\resources\Trainer.exe" "" "$INSTDIR\resources\Trainer.exe" 0
  CreateShortCut "$DESKTOP\Quantum Llama Browser.lnk" "$INSTDIR\resources\BrowserMode.exe" "" "$INSTDIR\resources\BrowserMode.exe" 0
!macroend

!macro customUnInstall
  Delete "$DESKTOP\Llama Trainer.lnk"
  Delete "$DESKTOP\Quantum Llama Browser.lnk"
!macroend
