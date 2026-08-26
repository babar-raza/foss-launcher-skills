from aspose.email_foss import msg

with msg.MsgReader.from_file(msg_path) as reader:
    cfb = reader.cfb_reader
    print(f"major_version={cfb.major_version} sector_size={cfb.sector_size}")

    header = reader.top_level_header
    print(f"recipient_count={header.recipient_count} attachment_count={header.attachment_count}")

    for entry in reader.iter_recipient_storages():
        print(f"recipient storage: {entry.name}")
