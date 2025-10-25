# #jeff Channel Configuration

To use Jeff, you need to add the **#jeff** channel to your MeshCore device.

## Channel Details

- **Channel Name**: `#jeff`
- **Channel Index**: `7`
- **Channel Secret**: `a3f7e9b12c4d6a8f5e2b9d7c3a8f4e1b`

## Add Channel via Web App

1. Go to https://app.meshcore.nz
2. Connect your device via USB/BLE
3. Navigate to **Channels**
4. Click **Add Channel**
5. Enter:
   - **Index**: `7`
   - **Name**: `#jeff`
   - **Secret**: `a3f7e9b12c4d6a8f5e2b9d7c3a8f4e1b`
6. Click **Save**

## Add Channel via Mobile App

1. Open MeshCore app (Android/iOS)
2. Connect to your device
3. Go to **Channels**
4. Tap **+** to add channel
5. Enter details above
6. Save

## Add Channel via Serial/CLI

If you have serial access to your device:

```bash
add-channel 7 #jeff a3f7e9b12c4d6a8f5e2b9d7c3a8f4e1b
save
```

## Verify

After adding, you should see `#jeff` in your channel list. Send a test message:

```
Test message on #jeff
```

You should see:
- Jeff responds on MeshCore
- Message appears in Discord #jeff channel

## Discord Bridge

Once the channel is added:
- All messages on MeshCore #jeff → Discord #jeff
- Jeff's responses → Discord (highlighted in green)
- Message format includes sender, text, timestamp
